import { useTranslation } from "react-i18next";
import { Construction } from "lucide-react";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/misc";

export function SoonPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader title={t(titleKey)} />
      <Card className="flex flex-col items-center px-6 py-16 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-lucht/20 text-nacht dark:text-lucht">
          <Construction className="h-6 w-6" />
        </div>
        <h2 className="mt-4 font-semibold">{t("soon.title")}</h2>
        <p className="mt-1 max-w-md text-sm text-muted">{t("soon.body")}</p>
      </Card>
    </>
  );
}
