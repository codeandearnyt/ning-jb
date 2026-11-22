"use client";

import { CHECKLISTS, GROUP_LABELS, type ChecklistGroup } from "@/lib/checklists";

interface ChecklistPickerProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

const ORDER: ChecklistGroup[] = ["code", "network", "physical", "prose"];

export function ChecklistPicker({
  id,
  value,
  onChange,
  disabled,
}: ChecklistPickerProps) {
  return (
    <select
      id={id}
      className="field-select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
    >
      <option value="">Infer from target</option>
      {ORDER.map((group) => (
        <optgroup key={group} label={GROUP_LABELS[group]}>
          {CHECKLISTS.filter((c) => c.group === group).map((c) => (
            <option key={c.id} value={c.id}>
              {c.label} — {c.items.length} items
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
