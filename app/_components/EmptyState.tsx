export default function EmptyState({ section = "analysis" }: { section: string }) {
  return (
    <section className="border border-dashed border-gray-300 rounded-xl w-full h-full p-8 text-center text-gray-500">
      <h1 className="text-xl font-semibold mb-2">No data yet</h1>
      <p>Upload a statement to see {section} here.</p>
    </section>
  );
}
