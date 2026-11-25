import unittest
from nexus_exchange.cockpit import help_for,drift,HELPS,fit_geometry,GREEN,PURPLE,BLACK


class CockpitTests(unittest.TestCase):
    def test_halt_and_resume_help_preserve_authority_boundary(self):
        self.assertIn("Stop new work",help_for("Emergency halt","TButton"))
        self.assertIn("never enables payments",help_for("Resume offline","TButton"))

    def test_financial_help_never_claims_real_money(self):
        self.assertIn("no real invoice",help_for("Preview simulation","TButton"))
        self.assertIn("No money moves",help_for("Model cash flow and reserve","TButton"))
        self.assertIn("made-up",help_for("Record synthetic receipt","TButton"))

    def test_known_button_labels_case_and_space(self):
        self.assertEqual(help_for("  Export  new CSV ","TButton"),HELPS["export new csv"])
        self.assertIn("not replaced",help_for("Export new CSV","TButton"))

    def test_unknown_controls_have_bounded_plain_help(self):
        self.assertLess(len(help_for("x"*10000,"TButton")),180)
        self.assertIn("Choose or clear",help_for("sam","TCheckbutton"))
        self.assertIn("Choose an option",help_for("","TCombobox"))
        self.assertIsNone(help_for("Title","TLabel"))

    def test_drift_wrap_and_pause_is_ui_only(self):
        x,y=drift(.99,.01,.03,-.04)
        self.assertAlmostEqual(x,.02)
        self.assertAlmostEqual(y,.97)
        self.assertEqual(drift(.3,.4,0,0),(.3,.4))

    def test_screen_geometry_is_bounded(self):
        class Screen:
            def winfo_screenwidth(self):return 1280
            def winfo_screenheight(self):return 800
        self.assertEqual(fit_geometry(Screen(),1080,820),"1114x700")

    def test_palette_distinct_and_high_contrast(self):
        def luminance(hexcolor):
            c=[int(hexcolor[i:i+2],16)/255 for i in (1,3,5)]
            c=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in c]
            return sum(x*y for x,y in zip(c,(.2126,.7152,.0722)))
        for color in (GREEN,PURPLE):
            self.assertGreater((luminance(color)+.05)/(luminance(BLACK)+.05),4.5)
        self.assertNotEqual(GREEN,PURPLE)


if __name__=="__main__":
    unittest.main()
