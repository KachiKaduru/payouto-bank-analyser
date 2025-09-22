import { useParserStore } from "../_store/useParserStore";

export default function ErrorSection() {
  const { error } = useParserStore();

  return (
    <section>
      {error && (
        <div className="mt-4 text-red-600 font-medium bg-red-50 border border-red-200 p-3 rounded-lg">
          {error}
        </div>
      )}
    </section>
  );
}
