from __future__ import annotations

import asyncio
from importlib import resources
from io import BytesIO

from kvui import GameManager

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from .context import ProfileRebindError, ProfileRebindPreview
from .tracker_view import CIVILIZATION_FLAG_FILES, CivilizationTrackerEntry

class AgeOfEmpiresIVManager(GameManager):
    base_title = "Age of Empires IV Client"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._flag_textures = {}
        self._tracker_signature = None

    def build(self):
        root = super().build()
        panel = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))

        heading = Label(
            text="AOE4World Match Tracking",
            size_hint_y=None,
            height=dp(36),
            font_size="20sp",
        )
        panel.add_widget(heading)

        credentials = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        self.profile_input = TextInput(
            text=str(self.ctx.profile_id or ""),
            hint_text="AOE4World profile ID",
            multiline=False,
            input_filter="int",
        )
        self.key_input = TextInput(
            hint_text="Optional AOE4World API key (custom/private games)",
            multiline=False,
            password=True,
            password_mask="•",
        )
        start_button = Button(text="Start Tracking", size_hint_x=None, width=dp(150))
        start_button.bind(on_release=self._start_tracking)
        self.correct_profile_button = Button(
            text="Correct Bound Profile",
            size_hint_x=None,
            width=dp(190),
        )
        self.correct_profile_button.bind(on_release=self._prepare_profile_rebind)
        credentials.add_widget(self.profile_input)
        credentials.add_widget(self.key_input)
        credentials.add_widget(start_button)
        credentials.add_widget(self.correct_profile_button)
        panel.add_widget(credentials)

        self.credential_message = Label(
            text="The profile ID is required and saved locally. The optional API key is never saved.",
            size_hint_y=None,
            height=dp(28),
        )
        panel.add_widget(self.credential_message)

        scroll = ScrollView()
        self.status_label = Label(
            text="",
            halign="left",
            valign="top",
            size_hint_y=None,
            padding=(dp(8), dp(8)),
        )
        self.status_label.bind(
            width=lambda widget, width: setattr(widget, "text_size", (width, None)),
            texture_size=lambda widget, size: setattr(widget, "height", max(size[1] + dp(16), dp(300))),
        )
        scroll.add_widget(self.status_label)
        panel.add_widget(scroll)

        self.add_client_tab("AOE4", panel, index=0)
        self._build_tracker_tab()
        Clock.schedule_interval(self._refresh_status, 1)
        self._refresh_status()
        return root

    def _start_tracking(self, _button) -> None:
        success, message = self.ctx.configure_credentials(self.profile_input.text, self.key_input.text)
        self._set_credential_message(success, message)

    def _prepare_profile_rebind(self, _button) -> None:
        self._set_credential_message(True, "Validating the corrected AOE4World profile...")
        asyncio.create_task(self._prepare_profile_rebind_async(), name="AOE4 profile correction preview")

    async def _prepare_profile_rebind_async(self) -> None:
        try:
            preview = await self.ctx.prepare_profile_rebind(self.profile_input.text, self.key_input.text)
        except ProfileRebindError as error:
            self._set_credential_message(False, str(error))
            return
        Clock.schedule_once(lambda _dt: self._show_rebind_confirmation(preview), 0)

    def _show_rebind_confirmation(self, preview: ProfileRebindPreview) -> None:
        progress_warning = (
            f"The AP server already confirms {preview.confirmed_checks} AOE4 check(s). "
            if preview.confirmed_checks
            else ""
        )
        goal_warning = "The slot has already reported goal completion. " if preview.goal_completed else ""
        warning = (
            f"Replace bound profile {preview.old_profile_id} with\n"
            f"{preview.new_profile_name} ({preview.new_profile_id})?\n\n"
            f"{progress_warning}{goal_warning}Previously submitted checks, delivered items, "
            "DeathLinks, and goal completion cannot be reversed. The correction will be recorded "
            "in AP DataStorage."
        )

        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        label = Label(text=warning, halign="left", valign="middle")
        label.bind(size=lambda widget, size: setattr(widget, "text_size", (size[0], None)))
        content.add_widget(label)
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel = Button(text="Cancel")
        confirm = Button(text="Confirm Profile Correction")
        buttons.add_widget(cancel)
        buttons.add_widget(confirm)
        content.add_widget(buttons)

        popup = Popup(
            title="Confirm AOE4World Profile Correction",
            content=content,
            size_hint=(0.78, 0.58),
            auto_dismiss=False,
        )
        cancel.bind(on_release=popup.dismiss)
        confirm.bind(on_release=lambda _button: self._confirm_profile_rebind(popup, preview))
        popup.open()

    def _confirm_profile_rebind(self, popup: Popup, preview: ProfileRebindPreview) -> None:
        popup.dismiss()
        self._set_credential_message(True, "Correcting the AP profile binding...")
        asyncio.create_task(
            self._confirm_profile_rebind_async(preview),
            name="AOE4 profile correction",
        )

    async def _confirm_profile_rebind_async(self, preview: ProfileRebindPreview) -> None:
        try:
            message = await self.ctx.rebind_profile(preview, self.key_input.text)
        except ProfileRebindError as error:
            self._set_credential_message(False, str(error))
            return
        self.profile_input.text = str(preview.new_profile_id)
        self._set_credential_message(True, message)

    def _set_credential_message(self, success: bool, message: str) -> None:
        self.credential_message.text = message
        self.credential_message.color = (0.35, 0.85, 0.45, 1) if success else (1, 0.35, 0.35, 1)

    def _build_tracker_tab(self) -> None:
        panel = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        panel.add_widget(
            Label(
                text="Civilization Tracker",
                size_hint_y=None,
                height=dp(36),
                font_size="20sp",
            )
        )
        self.tracker_summary = Label(
            text="Connect to an Age of Empires IV slot to view its civilization pool.",
            size_hint_y=None,
            height=dp(72),
            halign="left",
            valign="middle",
        )
        self.tracker_summary.bind(
            width=lambda widget, width: setattr(widget, "text_size", (width, None))
        )
        panel.add_widget(self.tracker_summary)

        scroll = ScrollView()
        self.tracker_content = GridLayout(
            cols=1,
            spacing=dp(6),
            padding=(dp(4), dp(4), dp(4), dp(12)),
            size_hint_y=None,
        )
        self.tracker_content.bind(minimum_height=self.tracker_content.setter("height"))
        scroll.add_widget(self.tracker_content)
        panel.add_widget(scroll)
        self.add_client_tab("Tracker", panel, index=1)

    def _refresh_tracker(self) -> None:
        entries = self.ctx.civilization_tracker_entries()
        total_progress = self.ctx.total_win_tracker_progress()
        signature = (bool(self.ctx.slot_data), entries, total_progress)
        if signature == self._tracker_signature:
            return
        self._tracker_signature = signature
        self.tracker_content.clear_widgets()

        if not self.ctx.slot_data:
            self.tracker_summary.text = (
                "Connect to an Age of Empires IV slot to view its civilization pool."
            )
            self._add_tracker_message("Tracker data is waiting for the AP slot connection.")
            return

        available = tuple(entry for entry in entries if entry.unlocked)
        pending = tuple(entry for entry in available if not entry.requirement_complete)
        locked = tuple(entry for entry in entries if not entry.unlocked)
        completed = sum(
            entry.required_wins > 0 and entry.requirement_complete for entry in available
        )
        required = sum(entry.required_wins > 0 for entry in available)
        earned_total, attainable_total, final_total_cap = total_progress
        if attainable_total is None:
            total_summary = f"Total wins: {earned_total} earned; no global cap. "
        else:
            total_summary = (
                f"Total wins: {earned_total} earned / {attainable_total} currently attainable"
                f" (final cap {final_total_cap}). "
            )
        self.tracker_summary.text = total_summary + (
            f"{len(available)} of {len(entries)} civilizations available. "
            f"{len(pending)} unlocked civilization(s) still need wins; "
            f"{completed}/{required} unlocked requirements complete."
        )

        self._add_tracker_section(
            "Still Need Civilization Wins (Unlocked)",
            pending,
            empty_message="Every currently unlocked civilization has completed its required wins.",
            row_kind="pending",
        )
        self._add_tracker_section(
            "Available Civilizations",
            available,
            empty_message="No civilizations are available yet.",
            row_kind="available",
        )
        self._add_tracker_section(
            "Locked Civilizations",
            locked,
            empty_message="All civilizations in this slot are unlocked.",
            row_kind="locked",
        )

    def _add_tracker_section(
        self,
        title: str,
        entries: tuple[CivilizationTrackerEntry, ...],
        *,
        empty_message: str,
        row_kind: str,
    ) -> None:
        heading = Label(
            text=f"{title} ({len(entries)})",
            size_hint_y=None,
            height=dp(38),
            font_size="18sp",
            halign="left",
            valign="middle",
            color=(0.82, 0.88, 1, 1),
        )
        heading.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
        self.tracker_content.add_widget(heading)
        if not entries:
            self._add_tracker_message(empty_message)
            return
        for entry in entries:
            self.tracker_content.add_widget(self._tracker_row(entry, row_kind))

    def _add_tracker_message(self, message: str) -> None:
        label = Label(
            text=message,
            size_hint_y=None,
            height=dp(42),
            halign="left",
            valign="middle",
            color=(0.68, 0.7, 0.75, 1),
            padding=(dp(8), 0),
        )
        label.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
        self.tracker_content.add_widget(label)

    def _tracker_row(self, entry: CivilizationTrackerEntry, row_kind: str) -> BoxLayout:
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(64),
            spacing=dp(12),
            padding=(dp(8), dp(5)),
        )
        flag = Image(
            texture=self._flag_texture(entry.civilization),
            size_hint_x=None,
            width=dp(94),
            fit_mode="contain",
        )
        if row_kind == "locked":
            flag.color = (0.45, 0.45, 0.45, 0.5)
        row.add_widget(flag)

        if row_kind == "locked":
            status = "Locked - receive its Civilization Unlock item"
            color = (0.56, 0.58, 0.63, 1)
        elif entry.required_wins == 0:
            status = (
                f"Unlocked - {entry.credited_wins} earned; "
                "no civilization-specific wins required"
            )
            color = (0.45, 0.85, 0.55, 1)
        else:
            attainable = (
                str(entry.attainable_wins)
                if entry.attainable_wins is not None
                else "unrestricted"
            )
        if row_kind != "locked" and entry.required_wins > 0 and entry.requirement_complete:
            status = (
                f"Complete - {entry.credited_wins} earned / {attainable} currently attainable / "
                f"{entry.required_wins} required"
            )
            color = (0.45, 0.85, 0.55, 1)
        elif row_kind != "locked" and entry.cap_blocked:
            status = (
                f"Win cap required - {entry.credited_wins} earned / {attainable} currently attainable / "
                f"{entry.required_wins} required"
            )
            color = (1, 0.72, 0.28, 1)
        elif row_kind == "pending":
            noun = "win" if entry.wins_remaining == 1 else "wins"
            status = (
                f"{entry.wins_remaining} {noun} remaining - {entry.credited_wins} earned / "
                f"{attainable} currently attainable / {entry.required_wins} required"
            )
            color = (1, 0.72, 0.28, 1)
        elif row_kind != "locked" and entry.required_wins > 0:
            status = (
                f"{entry.credited_wins} earned / {attainable} currently attainable / "
                f"{entry.required_wins} required"
            )
            color = (1, 0.82, 0.45, 1)

        details = BoxLayout(orientation="vertical", spacing=0)
        name_label = Label(
            text=entry.name,
            halign="left",
            valign="bottom",
            font_size="16sp",
            color=(0.92, 0.94, 1, 1) if row_kind != "locked" else (0.65, 0.66, 0.7, 1),
        )
        status_label = Label(
            text=status,
            halign="left",
            valign="top",
            font_size="13sp",
            color=color,
        )
        for label in (name_label, status_label):
            label.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
            details.add_widget(label)
        row.add_widget(details)
        return row

    def _flag_texture(self, civilization: str):
        if civilization not in self._flag_textures:
            filename = CIVILIZATION_FLAG_FILES[civilization]
            data = (
                resources.files(__package__)
                .joinpath("assets", "civilization_flags", filename)
                .read_bytes()
            )
            self._flag_textures[civilization] = CoreImage(
                BytesIO(data), ext="png"
            ).texture
        return self._flag_textures[civilization]

    def _refresh_status(self, *_args) -> None:
        self.status_label.text = "\n\n".join(self.ctx.status_lines())
        self._refresh_tracker()
