/**
 * Setup → Templates: the scenario picker, reused from ScenarioPicker.
 *
 * Lives inside Setup rather than on the Dashboard because loading a
 * scenario is really an act of populating session state, which is
 * what the rest of Setup is for. After a successful load we route the
 * user on to Setup → When so they see the horizon we just stamped in.
 */

import { FileDown, FileUp, Wand2 } from "lucide-react";
import { useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  useSessionState,
  useYamlExport,
  useYamlImport,
} from "@/api/hooks";
import { ScenarioPicker } from "@/components/ScenarioPicker";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function Templates() {
  const navigate = useNavigate();
  const { data } = useSessionState();
  const hasConfig =
    (data?.doctors?.length ?? 0) > 0 && (data?.stations?.length ?? 0) > 0;

  return (
    <div className="space-y-6">
      <Card className="border-indigo-200 bg-indigo-50/60 dark:border-indigo-900 dark:bg-indigo-950/30">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Wand2 className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
            <CardTitle className="text-sm">Start from a template</CardTitle>
          </div>
          <CardDescription className="text-xs">
            Each template ships a realistic team + station set + shift
            labels. Picking one fills the whole <strong>Setup</strong>{" "}
            area in one click; you can still tweak any field afterwards.
            {hasConfig && (
              <>
                {" "}Or{" "}
                <Link
                  to="/setup/when"
                  className="text-indigo-700 underline decoration-dotted underline-offset-2 dark:text-indigo-300"
                >
                  keep your current setup
                </Link>
                .
              </>
            )}
          </CardDescription>
        </CardHeader>
      </Card>

      <ScenarioPicker
        showHeader={false}
        onLoaded={() => navigate("/setup/when")}
      />

      <YamlImportExportCard />
    </div>
  );
}

function YamlImportExportCard() {
  const { data } = useSessionState();
  const importer = useYamlImport();
  const exporter = useYamlExport();
  const fileRef = useRef<HTMLInputElement>(null);
  const hasConfig =
    (data?.doctors?.length ?? 0) > 0 && (data?.stations?.length ?? 0) > 0;

  const loadYamlFromFile = async (file: File) => {
    try {
      const text = await file.text();
      await importer.mutateAsync(text);
      toast.success(`Loaded ${file.name}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load YAML");
    }
  };
  const saveYaml = async () => {
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
      toast.success("Config downloaded");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to save config");
    }
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Or load your own YAML</CardTitle>
        <CardDescription className="text-xs">
          Drop a config you exported earlier to resume editing. Good for
          recurring rosters with small tweaks.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div
          className="flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-4 text-center text-xs transition-colors hover:border-indigo-400 hover:bg-indigo-50/60 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/40"
          onDragOver={(e) => {
            e.preventDefault();
            e.currentTarget.classList.add("border-indigo-500");
          }}
          onDragLeave={(e) =>
            e.currentTarget.classList.remove("border-indigo-500")
          }
          onDrop={(e) => {
            e.preventDefault();
            e.currentTarget.classList.remove("border-indigo-500");
            const f = e.dataTransfer.files?.[0];
            if (f) loadYamlFromFile(f);
          }}
        >
          <FileUp className="h-6 w-6 text-slate-400" />
          <div>
            <p className="font-medium">Drop YAML here</p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              or use the button below
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".yaml,.yml,text/yaml,application/x-yaml"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) loadYamlFromFile(f);
              e.target.value = "";
            }}
          />
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => fileRef.current?.click()}
          >
            <FileUp className="h-4 w-4" />
            Load YAML
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={saveYaml}
            disabled={!hasConfig}
          >
            <FileDown className="h-4 w-4" />
            Save current config
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
