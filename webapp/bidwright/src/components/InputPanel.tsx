import { useState } from "react";

interface InputPanelProps {
  running: boolean;
  ready: boolean;
  onRun: (input: { useExample: boolean; rfp: File | null; profile: File | null; amendment: File | null }) => void;
}

type Source = "example" | "upload";

export function InputPanel({ running, ready, onRun }: InputPanelProps) {
  const [rfpSource, setRfpSource] = useState<Source>("example");
  const [profileSource, setProfileSource] = useState<Source>("example");
  const [rfpFile, setRfpFile] = useState<File | null>(null);
  const [profileFile, setProfileFile] = useState<File | null>(null);
  const [amendmentFile, setAmendmentFile] = useState<File | null>(null);

  const usingExample = rfpSource === "example" && profileSource === "example";
  const missingUpload = (rfpSource === "upload" && !rfpFile) || (profileSource === "upload" && !profileFile);
  const canRun = !running && (usingExample || !missingUpload);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canRun) return;
    onRun({
      useExample: usingExample,
      rfp: rfpSource === "upload" ? rfpFile : null,
      profile: profileSource === "upload" ? profileFile : null,
      amendment: amendmentFile,
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-50">Run a new bid analysis</h2>

      <div className="grid gap-5 sm:grid-cols-2">
        <SourceField
          title="1. RFP document"
          exampleLabel="Use example (Rivertown RFP)"
          source={rfpSource}
          onSourceChange={setRfpSource}
          file={rfpFile}
          onFileChange={setRfpFile}
          accept=".txt,.md,.pdf,.docx"
          inputId="rfp-upload"
          disabled={running}
        />
        <SourceField
          title="2. Company profile"
          exampleLabel="Use example (GreenPath Grounds)"
          source={profileSource}
          onSourceChange={setProfileSource}
          file={profileFile}
          onFileChange={setProfileFile}
          accept=".txt,.md,.json"
          inputId="profile-upload"
          disabled={running}
        />
      </div>

      <div className="mt-5">
        <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
          3. Amendment / addendum <span className="font-normal text-slate-400">(optional, upload only)</span>
        </label>
        <input
          type="file"
          accept=".txt,.md,.pdf,.docx"
          disabled={running}
          onChange={(e) => setAmendmentFile(e.target.files?.[0] ?? null)}
          className="block w-full cursor-pointer rounded-lg border border-slate-300 text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-indigo-700 hover:file:bg-indigo-100 disabled:opacity-60 dark:border-slate-700 dark:text-slate-300 dark:file:bg-slate-800 dark:file:text-indigo-300"
        />
      </div>

      {!ready && (
        <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          No model credentials detected on the server. Set <code>ANTHROPIC_API_KEY</code>, or configure AWS
          credentials for Bedrock, then restart the server.
        </p>
      )}

      <button
        type="submit"
        disabled={!canRun}
        className="mt-5 w-full rounded-lg bg-gradient-to-r from-indigo-600 to-blue-600 px-4 py-3 text-sm font-semibold text-white shadow transition hover:from-indigo-500 hover:to-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {running ? "Running BidWright…" : "Run BidWright"}
      </button>
      {missingUpload && !running && (
        <p className="mt-2 text-center text-xs text-slate-500 dark:text-slate-400">
          Upload both an RFP document and a company profile, or switch back to the bundled example.
        </p>
      )}
    </form>
  );
}

function SourceField({
  title,
  exampleLabel,
  source,
  onSourceChange,
  file,
  onFileChange,
  accept,
  inputId,
  disabled,
}: {
  title: string;
  exampleLabel: string;
  source: Source;
  onSourceChange: (s: Source) => void;
  file: File | null;
  onFileChange: (f: File | null) => void;
  accept: string;
  inputId: string;
  disabled: boolean;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">{title}</label>
      <div className="mb-2 flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onSourceChange("example")}
          className={`flex-1 rounded-md px-2 py-1.5 font-medium transition ${
            source === "example"
              ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-700 dark:text-indigo-300"
              : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
          }`}
        >
          {exampleLabel}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onSourceChange("upload")}
          className={`flex-1 rounded-md px-2 py-1.5 font-medium transition ${
            source === "upload"
              ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-700 dark:text-indigo-300"
              : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
          }`}
        >
          Upload a file
        </button>
      </div>
      {source === "upload" && (
        <input
          id={inputId}
          type="file"
          accept={accept}
          disabled={disabled}
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
          className="block w-full cursor-pointer rounded-lg border border-slate-300 text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-indigo-700 hover:file:bg-indigo-100 disabled:opacity-60 dark:border-slate-700 dark:text-slate-300 dark:file:bg-slate-800 dark:file:text-indigo-300"
        />
      )}
      {source === "upload" && file && (
        <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">Selected: {file.name}</p>
      )}
    </div>
  );
}
