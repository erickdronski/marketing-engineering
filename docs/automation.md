# Connect a delivery adapter

The toolkit ends at a local decision. A queue approval and an external delivery are separate records. For a first client, have the operator perform delivery manually and record its reference. Keep account credentials and real customer exports in the client’s own systems.

For an adapter, agree on the action, channel, account and content field before implementing a connector. The local gate can compare the text an adapter proposes with a reviewed item. The adapter still owns destination validation, authorization, scheduling and provider error handling.

1. Read the intended delivery and validate its account, recipients, attachments and links against the approved scope. Freeze the payload that will be sent.
2. Check the exact content and channel with `mktgkit gate check --action publish_post --channel content`, passing the body on standard input from the adapter. Continue only on exit zero. Keep credentials out of this call.
3. Persist an idempotency key for the client, destination, queue ID and version. Reserve it once before sending. Supply it to the provider if supported.
4. On acknowledgement, store the provider’s immutable receipt and delivery time, then record the live URL on the queue item. If the call times out after transmission, reconcile the provider receipt before retrying. An unknown delivery outcome goes to a person.
5. Exercise the adapter against a fake destination. A rejected item should cause zero external calls. Sending the same event twice should produce one delivery. Change the copy after approval and confirm the gate refuses it. Switch off the credential to rehearse a stop.

A file-based gate does not reserve an external action atomically. The delivery service needs its own durable duplicate protection and a way to recover a pending receipt. For agent tool calls, a Claude Code hook can apply the same local check to explicitly mapped tools. [Permissions and hooks](permissions.md)
