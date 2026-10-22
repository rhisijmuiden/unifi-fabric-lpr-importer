import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

/** Load a settings section into local form state and save it back. */
export function useSettingsForm<T extends Record<string, unknown>>(section: string) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["settings", section], queryFn: () => api<T>(`/settings/${section}`) });
  const [form, setForm] = useState<T | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (query.data && form === null) setForm(query.data);
  }, [query.data, form]);

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<T>(`/settings/${section}`, { method: "PUT", body }),
    onSuccess: (data) => {
      qc.setQueryData(["settings", section], data);
      setForm(data);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  const set = (key: keyof T, value: unknown) => {
    setSaved(false);
    setForm((f) => (f ? { ...f, [key]: value } : f));
  };

  return { form, set, save, saved, loading: query.isLoading };
}
