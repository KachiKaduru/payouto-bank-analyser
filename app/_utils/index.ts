// app/_utils.ts
/**
 * Safely parse JSON from mixed stdout that may contain logs before/after.
 * Works for both objects and arrays. Generic so callers can assert shape.
 */
export function parseOutput<T = unknown>(output: string): T {
  try {
    // Find first JSON opener
    const objStart = output.indexOf("{");
    const arrStart = output.indexOf("[");
    if (objStart === -1 && arrStart === -1) {
      throw new Error("No JSON start token found in output");
    }

    // Prefer object if it appears earlier (our parser returns an object)
    const start = objStart !== -1 && (arrStart === -1 || objStart < arrStart) ? objStart : arrStart;
    // const opener = output[start];

    // Find the matching closer by scanning and tracking braces/brackets
    let depth = 0;
    let end = -1;
    for (let i = start; i < output.length; i++) {
      const ch = output[i];
      if (ch === "{") depth += 1;
      if (ch === "}") depth -= 1;
      if (ch === "[") depth += 1;
      if (ch === "]") depth -= 1;
      if (depth === 0 && (ch === "}" || ch === "]")) {
        end = i + 1;
        break;
      }
    }

    if (end === -1) {
      throw new Error("Could not find end of JSON payload");
    }

    const jsonSlice = output.slice(start, end);
    return JSON.parse(jsonSlice) as T;
  } catch (err) {
    // Last resort: try plain JSON.parse on whole string
    try {
      return JSON.parse(output) as T;
    } catch {
      console.error("Failed to parse output:", err, "Output:", output);
      throw err;
    }
  }
}

// import { ParsedRow } from "../_types";

// export function parseOutput(output: string): ParsedRow[] {
//   try {
//     // Find the first "[" and last "]" in the string (JSON array boundaries)
//     const startIndex = output.indexOf("[");
//     const endIndex = output.lastIndexOf("]") + 1;

//     // If brackets are missing, return empty array
//     if (startIndex === -1 || endIndex === 0) {
//       console.warn("No valid JSON array found in output");
//       return [];
//     }

//     const jsonPart = output.slice(startIndex, endIndex);

//     const parsedData = JSON.parse(jsonPart);

//     return parsedData;
//   } catch (err) {
//     console.error("Failed to parse output:", err, "Output:", output);
//     return [];
//   }
// }
