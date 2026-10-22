import { useQuery } from "@tanstack/react-query";
import { api, type SystemInfo } from "./api";

export function useSystemInfo() {
  return useQuery({ queryKey: ["system-info"], queryFn: () => api<SystemInfo>("/system/info") });
}
