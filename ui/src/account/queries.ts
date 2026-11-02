import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, must, succeed, type Account } from "../api/client";
import type { Language } from "../i18n";

const WHILE_SIGNING_IN = 1000; // the browser or the code may finish at any moment
const WHILE_OFFLINE = 30 * 1000; // the service tries QS Mind again every five minutes, in the background
const OTHERWISE = 10 * 60 * 1000; // the service refreshes the account hourly, when it is asked

/** The QS Mind account on this computer: who is signed in, the offline lease, a sign-in under way. */
export function useAccount() {
  return useQuery({
    queryKey: ["account"],
    queryFn: () => must(api.GET("/account")),
    refetchInterval: (query) => {
      const account = query.state.data;
      if (account?.pending) return WHILE_SIGNING_IN;
      return account?.state === "offline" || account?.state === "expired" ? WHILE_OFFLINE : OTHERWISE;
    },
  });
}

function useSet() {
  const client = useQueryClient();
  return (account: Account) => client.setQueryData(["account"], account);
}

export function useSignIn() {
  const set = useSet();
  return useMutation({
    mutationFn: ({ language, code }: { language: Language; code: boolean }) =>
      must(api.POST(code ? "/account/sign-in/code" : "/account/sign-in", { body: { language } })),
    onSuccess: set,
  });
}

export function useCancelSignIn() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => succeed(api.DELETE("/account/sign-in")),
    onSuccess: () => client.invalidateQueries({ queryKey: ["account"] }),
  });
}

export function useSignOut() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => succeed(api.POST("/account/sign-out")),
    onSuccess: () => client.invalidateQueries({ queryKey: ["account"] }),
  });
}
