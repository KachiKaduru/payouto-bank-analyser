import { ParsedRow } from "../_types";

export function parseOutput(output: string): ParsedRow[] {
  try {
    // Find the first "[" and last "]" in the string (JSON array boundaries)
    const startIndex = output.indexOf("[");
    const endIndex = output.lastIndexOf("]") + 1;

    // If brackets are missing, return empty array
    if (startIndex === -1 || endIndex === 0) {
      console.warn("No valid JSON array found in output");
      return [];
    }

    const jsonPart = output.slice(startIndex, endIndex);

    const parsedData = JSON.parse(jsonPart);

    return parsedData;
  } catch (err) {
    console.error("Failed to parse output:", err, "Output:", output);
    return [];
  }
}

// JUST IN CASE THE FIRST ONE EVER FAILS, WE CAN TRY THIS ONE OUT AND SEE
// export function parseOutput(output: string): ParsedRow[] {
//   try {
//     // Clean the output by removing lines before the first [
//     const lines = output.split("\n");
//     let jsonStart = -1;
//     for (let i = 0; i < lines.length; i++) {
//       if (lines[i].trim().startsWith("[")) {
//         jsonStart = i;
//         break;
//       }
//     }
//     const jsonString = jsonStart >= 0 ? lines.slice(jsonStart).join("\n") : output;

//     // Find the first "[" and last "]"
//     const startIndex = jsonString.indexOf("[");
//     const endIndex = jsonString.lastIndexOf("]") + 1;

//     if (startIndex === -1 || endIndex === 0) {
//       console.warn("No valid JSON array found in output");
//       return [];
//     }

//     const jsonPart = jsonString.slice(startIndex, endIndex);
//     const parsedData = JSON.parse(jsonPart);
//     return Array.isArray(parsedData) ? parsedData : [];
//   } catch (err) {
//     console.error("Failed to parse output:", err, "Output:", output);
//     return [];
//   }
// }
