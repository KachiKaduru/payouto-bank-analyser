import { NextRequest, NextResponse } from "next/server";
import { writeFile, unlink } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";
import { spawnSync } from "child_process";
import { ParsedRow } from "../../_types";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file") as File;

    if (!file) {
      return NextResponse.json({ error: "No file uploaded" }, { status: 400 });
    }

    if (file.type !== "application/pdf") {
      return NextResponse.json(
        { error: "Invalid file type. Please upload a PDF." },
        { status: 400 }
      );
    }

    // Write PDF to temporary file
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    const tempPath = join(tmpdir(), `${Date.now()}_${file.name}`);
    await writeFile(tempPath, buffer);

    try {
      // Run Python script
      const result = spawnSync("python", [join(process.cwd(), "parser.py"), tempPath], {
        encoding: "utf-8",
        stdio: ["pipe", "pipe", "pipe"],
        maxBuffer: 50 * 1024 * 1024, // Increase buffer to 50MB
      });

      if (result.error) {
        console.error("Python execution error:", result.error);
        return NextResponse.json(
          { error: "Failed to execute Python script: " + result.error.message },
          { status: 500 }
        );
      }

      if (result.status !== 0) {
        console.error("Python script stderr:", result.stderr);
        return NextResponse.json(
          { error: "Python script failed: " + result.stderr },
          { status: 500 }
        );
      }

      // Parse Python output
      const output = result.stdout || "[]";
      let jsonData: ParsedRow[];
      try {
        jsonData = JSON.parse(output);
      } catch (err) {
        console.error("JSON parse error:", err, "Output:", output);
        return NextResponse.json({ error: "Invalid data returned from parser" }, { status: 500 });
      }

      return NextResponse.json(jsonData, { status: 200 });
    } finally {
      // Clean up temporary file
      await unlink(tempPath).catch((err) => console.error("Failed to delete temp file:", err));
    }
  } catch (err: any) {
    console.error("API error:", err);
    return NextResponse.json({ error: "Failed to parse PDF: " + err.message }, { status: 500 });
  }
}
