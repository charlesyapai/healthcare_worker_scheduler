import { FileDown, FileUp } from "lucide-react";
import { useRef } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useYamlExport, useYamlImport } from "@/api/hooks";
import { Button } from "@/components/ui/button";

export function YamlMenu() {
  const exporter = useYamlExport();
  const importer = useYamlImport();
  const fileRef = useRef<HTMLInputElement>(null);

  const save = async () => {
    try {
      const { yaml } = await exporter.mutateAsync();
      const blob = new Blob([yaml], { type: "application/x-yaml" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `roster_config_${new Date().toISOString().slice(0, 10)}.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      toast.success("YAML downloaded");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to export");
    }
  };

  const load = async (file: File) => {
    try {
      const text = await file.text();
      await importer.mutateAsync(text);
      toast.success(`Loaded ${file.name}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load YAML");
    }
  };

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={save}
        title="Save YAML (Ctrl+S)"
        aria-label="Save YAML"
      >
        <FileDown className="h-4 w-4" />
        <span className="hidden md:inline">Save YAML</span>
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => fileRef.current?.click()}
        title="Load YAML"
        aria-label="Load YAML"
      >
        <FileUp className="h-4 w-4" />
        <span className="hidden md:inline">Load YAML</span>
      </Button>
      <input
        ref={fileRef}
        type="file"
        accept=".yaml,.yml,text/yaml,application/x-yaml"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) load(f);
          e.target.value = "";
        }}
      />
    </>
  );
}
