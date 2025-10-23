import { NextRequest, NextResponse } from "next/server";
import { writeFile, unlink } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";
import { spawnSync } from "child_process";
import type { ParseResponse } from "../../_types";
import { parseOutput } from "@/app/_utils";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file") as File;
    const bank = formData.get("bank") as string; // required
    const password = (formData.get("password") as string) || ""; // optional

    if (!file) {
      return NextResponse.json({ error: "No file uploaded" }, { status: 400 });
    }
    if (!bank) {
      return NextResponse.json({ error: "No bank selected" }, { status: 400 });
    }
    if (file.type !== "application/pdf") {
      return NextResponse.json(
        { error: "Invalid file type. Please upload a PDF." },
        { status: 400 }
      );
    }

    // Save to temp
    const buffer = Buffer.from(await file.arrayBuffer());
    const tempPath = join(tmpdir(), `${Date.now()}_${file.name}`);
    await writeFile(tempPath, buffer);

    try {
      // Run the Python dispatch (returns { meta, transactions, checks })
      const projectRoot = process.cwd();
      const dispatchPath = join(projectRoot, "parsers", "dispatch.py");

      const result = spawnSync(
        "python",
        [
          dispatchPath,
          tempPath,
          "--bank",
          bank.toLowerCase(),
          ...(password ? ["--password", password] : []),
        ],
        {
          encoding: "utf-8",
          stdio: ["pipe", "pipe", "pipe"],
          maxBuffer: 50 * 1024 * 1024,
        }
      );

      if (result.error) {
        console.error("Python execution error:", result.error);
        return NextResponse.json(
          { error: `Failed to execute Python script: ${result.error.message}` },
          { status: 500 }
        );
      }

      if (result.status !== 0) {
        console.error("Python script stderr:", result.stderr);
        if (result.stderr.includes("Please provide a password")) {
          return NextResponse.json(
            { error: "Encrypted PDF detected. Please provide a password." },
            { status: 400 }
          );
        }
        return NextResponse.json(
          { error: `Python script failed: ${result.stderr}` },
          { status: 500 }
        );
      }

      // Parse stdout as a ParseResponse
      const output = result.stdout || "{}";
      let jsonData: ParseResponse;
      try {
        jsonData = parseOutput<ParseResponse>(output);
      } catch (err) {
        console.error("JSON parse error:", err, "Output:", output);
        return NextResponse.json(
          { error: "Invalid data returned from parser", details: String(err) },
          { status: 500 }
        );
      }

      // Very light validation
      if (
        !jsonData ||
        !("transactions" in jsonData) ||
        !("meta" in jsonData) ||
        !("checks" in jsonData)
      ) {
        return NextResponse.json({ error: "Parser returned unexpected shape." }, { status: 500 });
      }

      return NextResponse.json(jsonData, { status: 200 });
    } finally {
      try {
        // Only attempt to delete if it still exists
        await unlink(tempPath);
      } catch (err: unknown) {
        // Ignore "no such file" — it was already cleaned up
        if (typeof err === "object" && err !== null && "code" in err && (err as { code?: string }).code !== "ENOENT") {
          console.error("Failed to delete temp file:", err);
        }
      }
    }
  } catch (err: unknown) {
    console.error("API error:", err);
    return NextResponse.json(
      {
        error: "Failed to parse PDF: " + (err instanceof Error ? err.message : String(err)),
      },
      { status: 500 }
    );
  }
}
