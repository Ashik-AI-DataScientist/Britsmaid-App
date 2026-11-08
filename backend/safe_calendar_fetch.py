"""Bounded HTTPS calendar reads with DNS pinning and redirect re-validation."""
import http.client
import ipaddress
import socket
import ssl
import zlib
from urllib.parse import urljoin, urlsplit

MAX_FEED_BYTES = 2 * 1024 * 1024


class CalendarFetchError(ValueError):
    pass


def validate_url(url):
    try:
        parsed = urlsplit(url)
        if (len(url) > 8192 or parsed.scheme.lower() != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.fragment
                or any(ord(c) < 33 for c in url) or "\\" in url):
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii")
        if host.lower().rstrip(".") in ("localhost", "localhost.localdomain"):
            raise ValueError()
        return parsed, host
    except (ValueError, UnicodeError):
        raise CalendarFetchError("Use a public HTTPS calendar link without a username, password or custom port.") from None


def public_addresses(host):
    try:
        addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast for ip in addresses):
            raise ValueError()
        return addresses
    except (OSError, ValueError):
        raise CalendarFetchError("Calendar links must resolve only to public internet addresses.") from None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, port=443, timeout=15, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the validated address, while retaining hostname certificate checks.
        connection = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
        except BaseException:
            connection.close()
            raise


def fetch_calendar(url):
    for redirect in range(4):
        parsed, host = validate_url(url)
        address = public_addresses(host)[0]
        connection = PinnedHTTPSConnection(host, address)
        try:
            connection.request("GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                headers={"Host": host, "User-Agent": "Britsmaid/1.0", "Accept": "text/calendar,text/plain", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if redirect == 3 or not location:
                    raise CalendarFetchError("Too many calendar redirects. Use the final public HTTPS export link.")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise CalendarFetchError("The calendar provider did not return a usable feed. Check the export link.")
            length = response.getheader("Content-Length")
            if length and (not length.isdigit() or int(length) > MAX_FEED_BYTES):
                raise CalendarFetchError("The calendar feed is too large (maximum 2 MB).")
            data = response.read(MAX_FEED_BYTES + 1)
            if len(data) > MAX_FEED_BYTES:
                raise CalendarFetchError("The calendar feed is too large (maximum 2 MB).")
            encoding = response.getheader("Content-Encoding", "identity").lower()
            if encoding == "gzip":
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                data = decoder.decompress(data, MAX_FEED_BYTES + 1)
                if len(data) > MAX_FEED_BYTES or not decoder.eof or decoder.unused_data:
                    raise CalendarFetchError("The calendar feed exceeds the supported size or encoding.")
            elif encoding not in ("identity", ""):
                raise CalendarFetchError("The calendar feed uses an unsupported encoding.")
            return data.decode("utf-8-sig")
        except CalendarFetchError:
            raise
        except (OSError, ValueError, http.client.HTTPException, zlib.error):
            raise CalendarFetchError("The calendar feed could not be read securely. Check the export link and try again.") from None
        finally:
            connection.close()
    raise CalendarFetchError("Calendar redirect limit reached.")
