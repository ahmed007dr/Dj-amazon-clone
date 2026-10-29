/**
 * Renders a guide string, turning `**label**` into `<strong>`.
 *
 * ⚠️  Built from React nodes, never `dangerouslySetInnerHTML`.
 *
 *     The content is ours today, but an HTML-injecting renderer is a hole the
 *     day someone pastes a string from an email or a ticket. Here a `<script>`
 *     typed into a guide string is just text on the screen.
 *
 * ⚠️  `split` with a capturing group: the captured (bold) parts always land on
 *     the odd indexes, so an unmatched `**` simply stays as literal text
 *     instead of swallowing the rest of the sentence.
 */
export function Inline({ text }: { text: string }) {
  const parts = text.split(/\*\*([\s\S]+?)\*\*/g);

  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? <strong key={index}>{part}</strong> : part,
      )}
    </>
  );
}
