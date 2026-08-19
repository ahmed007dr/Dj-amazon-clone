"""
External gateway adapters.

⚠️  **Sandbox verification is required before production.**

    The structure, the signatures and the fields are written against the known
    Paymob and Fawry contracts, but they **have not been tested against a real
    account** — there is no account and no keys yet. Gateways change field names
    and endpoint versions without broad notice.

    Before going live:
      1. Open a sandbox account.
      2. Add the keys from the admin panel (test mode).
      3. **Register the events URL in the gateway's own panel**:

             https://<host>/api/v1/payments/webhooks/<gateway code>/

         One URL per gateway, and its code is `PaymentProvider.code`.

         ⚠️  An endpoint the gateway cannot reach means orders left "processing"
             while the money is collected — a failure that appears in no log of
             ours, because nothing arrived at all.

      4. Run a complete operation: payment · webhook · refund.
      5. Correct any differing field name — the code records the full raw
         response in `PaymentTransaction.provider_response` and the complete
         inbound event in `WebhookEvent.payload`, so the difference shows immediately.

⚠️  **The signature arrives from two different places**: Paymob in the URL
    parameter (`?hmac=…`) and Fawry in the body (`messageSignature`). Each reads
    it in its own `parse_webhook` — and reading it from the wrong place refuses
    every valid event silently.

⚠️  The governing principle in both files: **no silent success.**

    Any unexpected response is treated as a failure, with its raw body saved.
    An optimistic inference ("no error ⟵ it worked") marks an order paid with no money.
"""
