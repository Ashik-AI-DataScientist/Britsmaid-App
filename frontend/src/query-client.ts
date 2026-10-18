// One QueryClient for the whole app; the provider in app/_layout.tsx uses
// this instance. Import it for cache calls outside components, for example
// queryClient.invalidateQueries or setQueryData in websocket or push
// handlers; inside components useQueryClient() returns this same instance.
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15000, retry: (attempt, error: Error & { status?: number }) => attempt < 1 && (!error.status || error.status >= 500) },
    mutations: { retry: false },
  },
});
