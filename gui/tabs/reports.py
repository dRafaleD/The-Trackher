from __future__ import annotations


class ReportsMixin:
    """Render scan result summaries in the shared terminal widget."""

    def _print_remediation_actions(self, remediation: dict):
        if not remediation or not remediation.get("available"):
            return

        self.print_to_terminal("  Remediation / Privacy Actions")
        self.print_to_terminal(
            f"    {remediation.get('item_count', 0)} findings include "
            f"{remediation.get('action_count', 0)} official action links."
        )
        for item in remediation.get("items", []):
            self.print_to_terminal(
                f"    {item.get('platform', 'Unknown')} — {item.get('status', 'FOUND')}"
            )
            for action in item.get("actions", []):
                self.print_to_terminal(
                    f"      • {action.get('label', 'Action')}: {action.get('url', '')}"
                )

    def _print_correlation_summary(self, correlation: dict):
        if not correlation or not correlation.get("available"):
            return

        self.print_to_terminal("  Identity Correlation")
        self.print_to_terminal(
            f"    {correlation.get('count', 0)} likely cross-platform identity links."
        )
        for item in correlation.get("items", []):
            self.print_to_terminal(
                f"    {item.get('confidence', 'LOW')} {item.get('summary', 'Unknown pair')} "
                f"({item.get('confidence_score', 0)}/100)"
            )
            for evidence in item.get("evidence", []):
                marker = "✓" if evidence.get("strength") in {"strong", "medium"} else "~"
                label = evidence.get("label", "signal")
                value = evidence.get("value", "")
                suffix = f": {value}" if value else ""
                self.print_to_terminal(f"      {marker} {label}{suffix}")
            for penalty in item.get("penalties", []):
                self.print_to_terminal(f"      ! {penalty.get('label', 'penalty')}")
        self.print_to_terminal(f"    {correlation.get('disclaimer', '')}")

    def _print_risk_summary(self, risk: dict):
        self.print_to_terminal("  Digital Footprint Risk Score")
        self.print_to_terminal(f"    {risk['score']}/100 ({risk['level']})")
        for reason in risk.get("reasons", []):
            sample = ", ".join(str(item) for item in reason.get("evidence", [])[:4])
            if len(reason.get("evidence", [])) > 4:
                sample += ", ..."
            self.print_to_terminal(
                f"    [+{reason['points']}] {reason['summary']}: {sample}"
            )
        self.print_to_terminal(f"    {risk['disclaimer']}")

    def _print_history_summary(self, history: dict):
        self.print_to_terminal("  SCAN DIFF")
        if not history.get("enabled", True):
            self.print_to_terminal("    Local scan history is disabled for this run.")
        elif not history.get("available"):
            self.print_to_terminal(f"    {history.get('message', 'No previous matching scan.')}")
        else:
            previous_risk = history.get("previous", {}).get("risk", {})
            current_risk = history.get("current", {}).get("risk", {})
            previous_profile = history.get("previous", {}).get("profile", "standard")
            current_profile = history.get("current", {}).get("profile", "standard")
            delta = int(history.get("risk_change", {}).get("value", 0))
            if delta > 0:
                change_label = f"↑ {delta}"
            elif delta < 0:
                change_label = f"↓ {abs(delta)}"
            else:
                change_label = "0"
            self.print_to_terminal(
                f"    Previous Risk: {previous_risk.get('score', 0)} {previous_risk.get('level', 'LOW')}"
            )
            self.print_to_terminal(
                f"    Current Risk:  {current_risk.get('score', 0)} {current_risk.get('level', 'LOW')}"
            )
            self.print_to_terminal(f"    Previous Profile: {previous_profile}")
            self.print_to_terminal(f"    Current Profile:  {current_profile}")
            self.print_to_terminal(f"    Change: {change_label}")
            self.print_to_terminal(f"    New: {len(history.get('new_findings', []))}")
            self.print_to_terminal(f"    Resolved: {len(history.get('resolved_findings', []))}")
            self.print_to_terminal(f"    Unchanged: {len(history.get('unchanged_findings', []))}")
            if history.get("profile_mismatch"):
                self.print_to_terminal(f"    {history.get('coverage_warning', '')}")
