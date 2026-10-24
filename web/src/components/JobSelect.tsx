import { Link } from "react-router-dom";
import type { Job } from "../api/types";
import { Select } from "./ui";

export function JobSelect({
  items,
  value,
  onChange,
  loading,
  id = "result-job",
}: {
  items: Job[];
  value: string;
  onChange: (id: string) => void;
  loading?: boolean;
  id?: string;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-[260px]">
        <Select
          id={id}
          label="Job"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={loading || items.length === 0}
          hint={
            !loading && items.length === 0
              ? "No jobs exist yet. Create a job with inputs to see results here."
              : "Results are read from the records this job persisted."
          }
        >
          {items.length === 0 ? <option value="">No jobs</option> : null}
          {items.map((j) => (
            <option key={j.id} value={j.id}>
              {j.display_id} · {j.state.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
      </div>
      {value ? (
        <Link to={`/jobs/${value}`} className="link pb-2.5 text-xs">
          Open job
        </Link>
      ) : null}
    </div>
  );
}
