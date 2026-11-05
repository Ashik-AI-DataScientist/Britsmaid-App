import { useQuery } from "@tanstack/react-query";
import { privateFileUrl } from "@/src/api";
import { useAuth } from "@/src/auth";

// Tickets can display one file only. Login credentials never enter image URLs.
export function useMediaUrl(id?: string, src?: string) {
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ["media-ticket", user?.id, id],
    queryFn: () => privateFileUrl(id!),
    enabled: !!user && !!id && !src,
    staleTime: 60000,
    gcTime: 0,
    refetchOnWindowFocus: true,
    retry: 1,
  });
  return { uri: src || (user ? query.data : undefined), error: query.isError,
    retry: async () => { if (id && !src) return query.refetch(); } };
}
