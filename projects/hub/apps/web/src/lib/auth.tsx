import { useMutation, useQueryClient } from '@tanstack/react-query'
import { admin } from './api'

const ME_KEY = ['admin', 'me'] as const

/** The password login (`AdminLogin.tsx`): the only thing left in this module since
 *  `useAdmin` and `useLogout` moved into `@/lib/me`'s merged `useMe`/`useLogout`
 *  (REB-279). `AdminLogin.tsx` itself is unreferenced by the router from this PR on,
 *  kept only because REB-281 deletes it together with the password routes it calls
 *  (design record 2026-09-17 §1, "Password login"). */
export function useLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      admin.login(email, password),
    onSuccess: (me) => client.setQueryData(ME_KEY, me),
  })
}
