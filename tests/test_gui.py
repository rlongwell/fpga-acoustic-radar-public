import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from radar import gui
    from radar.localization import Solver
    from radar.protocol import WINDOW


@unittest.skipUnless(HAS_QT, "Use .venv/bin/python for GUI tests")
class DashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = Path(self.directory.name) / "gui.json"
        self.settings.write_text(json.dumps({"array_layout": "rectangle", "column_mm": 36, "row_mm": 55, "measured": False,
                                              "unrelated": "preserve"}))
        self.setting_patch = patch.object(gui, "SETTINGS", self.settings)
        self.setting_patch.start()
        self.window = gui.Dashboard()
        self.solver = Solver(36, 55)

    def tearDown(self):
        self.window.close()
        self.setting_patch.stop()
        self.directory.cleanup()

    def accept(self, sequence):
        self.window.accept_frame(replace(self.solver.demo(40, sequence), source="L"))

    def test_old_rectangle_settings_open_current_hex_without_inheriting_calibration(self):
        self.window.close()
        self.settings.write_text(json.dumps({"measured": True, "swap_mic4_mic5": True,
                                             "row_mm": 55, "gate_db": -17}))
        self.window = gui.Dashboard()
        self.assertEqual(self.window.layout_choice.currentData(), "hexagon")
        self.assertFalse(self.window.hex_measured)
        self.assertEqual(self.window.make_solver().positions[0], (-0.02286, 0.0381))
        self.assertTrue(self.window.swap_mics.isHidden())
        self.window.temperature.setValue(26)
        self.window.close()
        self.window = gui.Dashboard()
        self.assertEqual(self.window.temperature.value(), 26)
        self.assertEqual(self.window.gate_slider.value(), -17)

    def test_old_hex_calibration_moves_once_with_the_physical_positions(self):
        self.window.close()
        old = [(46, 1), (22, 38), (-23, 39), (-45, 0), (-22, -38), (23, -37)]
        expected = ((-23, 37), (22, 38), (45, 0), (23, -39), (-22, -38), (-46, -1))
        self.settings.write_text(json.dumps({"hex_ports_mm": old, "hex_measured": True}))
        for opening in range(2):
            with self.subTest(opening=opening):
                self.window = gui.Dashboard()
                self.assertEqual(self.window.polar.ports_mm, expected)
                self.assertEqual(self.window.make_solver().positions,
                                 tuple((x / 1000, y / 1000) for x, y in expected))
                self.assertTrue(self.window.hex_measured)
                self.assertEqual([label.text() for label in self.window.mic_labels],
                                 ["M1 · Upper left · JE8", "M2 · Upper right · JE9", "M3 · Right · JE10",
                                  "M4 · Lower right · JE7", "M5 · Lower left · JE4", "M6 · Left · JE3"])
                self.window.close()

    def test_harness_lower_left_calibration_migrates_to_opposite_view_once(self):
        self.window.close()
        previous = [(-23, 39), (22, 37), (46, 1), (24, -36), (-21, -40), (-47, 2)]
        self.settings.write_text(json.dumps({"hex_ports_mm": previous, "hex_measured": True,
                                            "hex_port_order": "upper-left-clockwise"}))
        for _ in range(2):
            self.window = gui.Dashboard()
            self.assertEqual(self.window.ports_mm, ((-24, 36), (21, 40), (47, -2),
                                                   (23, -39), (-22, -37), (-46, -1)))
            self.assertTrue(self.window.hex_measured)
            self.window.close()

    def test_live_hex_bearings_and_meters_follow_the_new_view(self):
        w = self.window
        w.layout_choice.setCurrentIndex(0)
        w.gate_enabled.setChecked(False)
        w.reject_reflections.setChecked(False)
        solver = Solver()
        for seq, old_angle in enumerate((0, 40, 90, 160, 180, 235, 270, 315), 1):
            frame = replace(solver.demo(old_angle, seq), source="L")
            w.accept_frame(frame)
            self.assertTrue(w.polar.result.valid)
            expected = (old_angle + 180) % 360
            self.assertLessEqual(abs((w.polar.result.angle - expected + 180) % 360 - 180), 2)
        for old_channel, new_channel in enumerate((3, 4, 5, 0, 1, 2)):
            energy = [0]*6
            energy[old_channel] = WINDOW * 40000
            w.accept_frame(replace(frame, energy=tuple(energy)))
            self.assertEqual(max(range(6), key=w.polar.mic_levels.__getitem__), new_channel)
            self.assertEqual(max(range(6), key=lambda mic: w.levels[mic][0].value()), new_channel)
        # Rerender the same raw frame after a layout change.
        w.layout_choice.setCurrentIndex(1)
        self.assertEqual(max(range(6), key=w.polar.mic_levels.__getitem__), 5)

    def test_two_live_channels_cannot_display_a_hex_bearing_at_either_gate_setting(self):
        self.window.layout_choice.setCurrentIndex(0)
        frame = replace(self.window.make_solver().demo(270, 1), source="L",
                        energy=(0, 0, 4000000, 5000000, 0, 0))
        self.window.gate_slider.setValue(0)
        self.window.accept_frame(frame)
        self.assertIsNone(self.window.polar.result)
        self.assertIn("Quiet: 2, 3, 4, 5", self.window.details.text())
        self.window.gate_enabled.setChecked(False)
        self.assertFalse(self.window.polar.result.valid)
        self.assertIn("Quiet: 2, 3, 4, 5", self.window.details.text())

    def test_redraw_does_not_confirm_and_raw_is_opt_in(self):
        self.accept(1)
        self.assertFalse(self.window.polar.result.valid)
        for _ in range(4):
            self.window.refresh()
        self.assertFalse(self.window.polar.result.valid)
        self.assertIsNone(self.window.polar.raw_result)
        self.accept(2)
        self.assertTrue(self.window.polar.result.valid)
        self.assertTrue(self.window.polar.provisional)
        self.window.raw_response.setChecked(True)
        self.assertIsNotNone(self.window.polar.raw_result)

    def test_stale_stream_clears_marker(self):
        self.accept(1)
        self.accept(2)
        self.window.worker = object()  # No serial session; only the timeout path.
        try:
            self.window.last_frame_time = time.monotonic() - 1.1
            self.window.check_stale()
            self.assertIsNone(self.window.frame)
            self.assertIsNone(self.window.polar.result)
            self.assertEqual(self.window.plot_status.text(), "Stale bearing cleared")
        finally:
            self.window.worker = None

    def test_compass_bounds_stay_fixed_as_live_text_changes(self):
        w = self.window
        w.layout_choice.setCurrentIndex(0)
        w.reject_reflections.setChecked(False)
        w.raw_response.setChecked(True)
        w.show()
        live = replace(w.make_solver().demo(270, 1), source="L")
        for theme in ("dark", "light"):
            w.theme = theme
            w.apply_theme()
            for width in (775, 1050, 1320):
                with self.subTest(theme=theme, width=width):
                    w.resize(width, 730)
                    w.board_status("Waiting for Zybo")
                    self.app.processEvents()
                    bounds = w.polar.geometry()
                    for energy in ((0,) * 6, (WINDOW * 16,) * 6, live.energy):
                        w.accept_frame(replace(live, energy=energy))
                        self.app.processEvents()
                        self.assertEqual(w.polar.geometry(), bounds)
                        for label in (w.bearing, w.plot_status, w.details):
                            self.assertLessEqual(label.heightForWidth(label.width()), label.height())
                    self.assertIn("090°", w.bearing.text())

    def test_filming_view_tracks_chords_and_keeps_compass_fixed(self):
        w = self.window
        w.layout_choice.setCurrentIndex(0)
        w.reject_reflections.setChecked(False)
        w.gate_slider.setValue(-30)
        w.show()
        w.activateWindow()
        self.app.processEvents()
        initial = w.size()
        QTest.keyClick(w, Qt.Key.Key_F11)
        self.app.processEvents()
        self.assertTrue(w.isFullScreen())
        self.assertTrue(w.sidebar.isHidden())
        self.assertTrue(w.history_strip.isHidden())
        self.assertTrue(w.bearing.isHidden())
        bounds = w.polar.geometry()
        solver = w.make_solver()
        for seq, (angle, level) in enumerate(((0, 10000), (0, 1), (180, 14000)), 1):
            energy = tuple(WINDOW * level * (i+1) // 6 for i in range(6))
            w.accept_frame(replace(solver.demo(angle, seq), source="L", energy=energy))
            self.app.processEvents()
            self.assertEqual(w.polar.geometry(), bounds)
            if level == 1:
                self.assertFalse(w.trace.arcs)
                self.assertIsNone(w.trace.history[-1].angle)
            else:
                self.assertLessEqual(abs((w.trace.arcs[-1].angle - (angle + 180) + 180) % 360 - 180), 2)
                self.assertIn("Live", w.film_status.text())
                self.assertGreater(w.polar.mic_levels[2], w.polar.mic_levels[3])
        w.refresh()
        self.assertEqual(len(w.trace.history), 3)
        self.assertFalse(w.polar.grab().isNull())
        QTest.keyClick(w, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(w.isFullScreen())
        self.assertTrue(w.sidebar.isVisible())
        self.assertEqual(w.size(), initial)
        self.assertEqual(w.gate_slider.value(), -30)
        w.diagnostics.setChecked(True)
        self.assertTrue(w.history_strip.isVisible())
        self.assertTrue(w.bearing.isVisible())
        w.board_status("Disconnected")
        self.assertFalse(w.trace.history)
        self.assertTrue(all(level <= -60 for level in w.polar.mic_levels))

    def test_settings_survive_themes_and_restart(self):
        self.assertEqual(self.window.filter_strength.currentData(), "gentle")
        self.window.filter_strength.setCurrentIndex(1)
        self.window.swap_mics.setChecked(True)
        self.window.gate_slider.setValue(-31)
        self.window.gate_enabled.setChecked(False)
        self.window.raw_response.setChecked(True)
        self.window.reject_reflections.setChecked(False)
        self.window.toggle_theme()
        self.window.close()
        self.window = gui.Dashboard()
        self.assertTrue(self.window.raw_response.isChecked())
        self.assertFalse(self.window.reject_reflections.isChecked())
        self.assertEqual(self.window.filter_strength.currentData(), "strong")
        self.assertFalse(self.window.filter_strength.isEnabled())
        self.assertTrue(self.window.swap_mics.isChecked())
        self.assertEqual(self.window.gate_slider.value(), -31)
        self.assertFalse(self.window.gate_enabled.isChecked())
        self.assertFalse(self.window.gate_slider.isEnabled())
        self.assertEqual(self.window.make_solver().positions[3], (0.0, -0.0275))
        self.assertEqual(self.window.make_solver().positions[4], (-0.036, -0.0275))
        self.assertEqual(self.window.theme, "light")
        self.assertEqual(self.window.column.value(), 36)
        self.assertEqual(self.window.row.value(), 55)
        self.assertFalse(self.window.measured.isChecked())
        self.assertEqual(json.loads(self.settings.read_text())["unrelated"], "preserve")

    def test_filter_and_geometry_changes_reset_confirmation(self):
        self.accept(1)
        self.accept(2)
        self.window.reject_reflections.setChecked(False)
        self.assertTrue(self.window.polar.result.valid)
        self.window.reject_reflections.setChecked(True)
        self.assertFalse(self.window.polar.result.valid)
        self.accept(3)
        self.assertTrue(self.window.polar.result.valid)
        self.window.column.setValue(37)
        self.assertFalse(self.window.polar.result.valid)

    def test_gate_hides_both_responses_but_keeps_meters_live(self):
        self.window.reject_reflections.setChecked(False)
        self.window.raw_response.setChecked(True)
        self.window.gate_slider.setValue(-20)
        frame = replace(self.solver.demo(40, 1), source="L", energy=(WINDOW * 200,) * 6)
        self.window.accept_frame(frame)
        self.assertIsNone(self.window.polar.result)
        self.assertIsNone(self.window.polar.raw_result)
        self.assertEqual(self.window.bearing.text(), "Below level gate")
        self.assertGreater(self.window.levels[0][0].value(), -60)
        self.assertIn("-31.2", self.window.array_level.text())
        # Changing the slider redraws the already received frame immediately.
        self.window.gate_slider.setValue(-40)
        self.assertTrue(self.window.polar.result.valid)
        self.assertIsNotNone(self.window.polar.raw_result)
        self.window.gate_slider.setValue(-10)
        self.assertIsNone(self.window.polar.result)
        self.assertIsNone(self.window.polar.raw_result)

    def test_gate_can_be_disabled_and_slider_uses_keyboard(self):
        self.window.reject_reflections.setChecked(False)
        self.window.gate_slider.setValue(-20)
        QTest.keyClick(self.window.gate_slider, Qt.Key.Key_Right)
        self.assertEqual(self.window.gate_slider.value(), -19)
        self.window.accept_frame(replace(self.solver.demo(40, 1), energy=(WINDOW * 200,) * 6))
        self.assertIsNone(self.window.polar.result)
        self.window.gate_enabled.setChecked(False)
        self.assertFalse(self.window.gate_slider.isEnabled())
        self.assertTrue(self.window.polar.result.valid)

    def test_silent_mic_does_not_lower_gate_level(self):
        frame = self.solver.demo(40, 1)
        power = WINDOW * 2000
        normal = replace(frame, energy=(power,) * 6)
        silent_two = replace(frame, energy=(power, 0, power, power, power, power))
        self.assertAlmostEqual(gui.array_level_db(normal), gui.array_level_db(silent_two))
        self.assertAlmostEqual(gui.array_level_db(normal), 10 * math.log10(2000 / 512**2))
        self.assertLess(gui.array_level_db(replace(frame, energy=(0,) * 6)), -60)

    def test_gate_closure_resets_reflection_confirmation(self):
        self.window.gate_slider.setValue(-22)
        def frame(seq, power):
            return replace(self.solver.demo(40, seq), source="L", energy=(WINDOW * power,) * 6)
        self.window.accept_frame(frame(1, 10000))
        self.window.accept_frame(frame(2, 10000))
        self.assertTrue(self.window.polar.result.valid)
        self.window.accept_frame(frame(3, 100))
        self.assertIsNone(self.window.polar.result)
        self.window.accept_frame(frame(4, 10000))
        self.assertFalse(self.window.polar.result.valid)
        self.window.accept_frame(frame(5, 10000))
        self.assertTrue(self.window.polar.result.valid)

    def test_gate_opens_at_threshold_and_closes_below(self):
        self.window.reject_reflections.setChecked(False)
        self.window.gate_slider.setValue(0)
        frame = replace(self.solver.demo(40, 1), energy=(WINDOW * 512**2,) * 6)
        self.window.accept_frame(frame)
        self.assertIsNotNone(self.window.polar.result)
        self.window.accept_frame(replace(frame, sequence=2, energy=(WINDOW * 512**2 - 1,) * 6))
        self.assertIsNone(self.window.polar.result)

    def test_invalid_saved_gate_threshold_has_safe_default(self):
        self.window.close()
        settings = json.loads(self.settings.read_text())
        settings['gate_db'] = 'invalid'
        self.settings.write_text(json.dumps(settings))
        self.window = gui.Dashboard()
        self.assertEqual(self.window.gate_slider.value(), -22)


if __name__ == "__main__":
    unittest.main()
