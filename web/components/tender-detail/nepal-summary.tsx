"use client";

import type { ReactNode } from "react";

import { Money } from "@/components/money";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { TenderRecord } from "@/lib/api/tenderly";
import { formatDate } from "@/lib/nepal/calendar";
import { EnumText, usePrefs } from "@/lib/prefs";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[11rem_1fr] gap-2 border-b py-2 text-sm last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

/** An AD ISO date in both calendars, the preferred one first. */
function BothCalendars({ adIso }: { adIso: string }) {
  const { calendar, lang } = usePrefs();
  const other = calendar === "BS" ? "AD" : "BS";
  return (
    <div className="flex flex-col">
      <span className="font-medium">
        {formatDate(adIso, calendar, lang)} {calendar}
      </span>
      <span className="text-xs text-muted-foreground">
        {formatDate(adIso, other, lang)} {other}
      </span>
    </div>
  );
}

/** Nepal-specific facts of the notice, as the deterministic layer read them. */
export function NepalSummary({
  record,
}: {
  record: TenderRecord | null | undefined;
}) {
  const { t } = usePrefs();
  const none = (
    <span className="text-muted-foreground">{t("td.notStated")}</span>
  );
  if (!record) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("td.section.nepal")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            {t("td.fields.empty")}
          </p>
        </CardContent>
      </Card>
    );
  }
  const due = record.bid_security_due;
  const amount = due?.amount_npr ?? record.bid_security?.amount_npr ?? null;
  const percent = record.bid_security?.percent;
  const validityDays = record.bid_security?.validity_days;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("td.section.nepal")}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl>
          <Row label={t("td.nepal.procurementType")}>
            <EnumText kind="procurement_type" value={record.procurement_type} />
          </Row>
          <Row label={t("td.nepal.method")}>
            <EnumText kind="method" value={record.method} />
          </Row>
          <Row label={t("td.nepal.buyerLevel")}>
            <EnumText kind="buyer_level" value={record.buyer_level} />
          </Row>
          <Row label={t("td.nepal.evaluation")}>
            {record.evaluation_method ? (
              <EnumText
                kind="evaluation_method"
                value={record.evaluation_method}
              />
            ) : (
              none
            )}
          </Row>
          <Row label={t("td.nepal.bidSecurity")}>
            {amount != null ? (
              <div>
                <Money amount={amount} />
                {percent != null && (
                  <div className="text-xs text-muted-foreground">
                    {t("td.nepal.percentOfPrice", { p: percent })}
                  </div>
                )}
                {due?.basis && (
                  <div className="text-xs text-muted-foreground">
                    {due.basis}
                  </div>
                )}
              </div>
            ) : percent != null ? (
              t("td.nepal.percentOfPrice", { p: percent })
            ) : (
              none
            )}
          </Row>
          <Row label={t("td.nepal.bidSecurityUntil")}>
            {due?.valid_until ? (
              <BothCalendars adIso={due.valid_until} />
            ) : validityDays != null ? (
              t("td.nepal.daysFromDeadline", { n: validityDays })
            ) : (
              none
            )}
          </Row>
          <Row label={t("td.nepal.bidValidity")}>
            {record.bid_validity_days != null
              ? t("td.nepal.days", { n: record.bid_validity_days })
              : none}
          </Row>
          <Row label={t("td.nepal.performance")}>
            {record.performance_security_percent != null
              ? t("td.nepal.percentOfContract", {
                  p: record.performance_security_percent,
                })
              : none}
          </Row>
          <Row label={t("td.nepal.domestic")}>
            {t(record.domestic_preference ? "td.yes" : "td.no")}
          </Row>
          <Row label={t("td.nepal.jv")}>
            {record.jv_allowed == null
              ? none
              : t(record.jv_allowed ? "td.yes" : "td.no")}
          </Row>
        </dl>
      </CardContent>
    </Card>
  );
}
