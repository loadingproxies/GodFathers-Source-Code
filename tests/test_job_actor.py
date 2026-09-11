import unittest

from app.core.job_actor import JobActor
from app.core.jobs import job_list_band


class JobActorHaltTests(unittest.TestCase):
    def test_global_halt_stops_mouse_moves(self):
        from app.core.input import clicks_halted, glide_to, scroll_at, set_clicks_halted

        set_clicks_halted(True)
        try:
            self.assertTrue(clicks_halted())
            self.assertFalse(glide_to(10, 10, steps=4))
            self.assertFalse(scroll_at(10, 10, steps=-1))
        finally:
            set_clicks_halted(False)
        self.assertFalse(clicks_halted())

    def test_halt_aborts_sleep(self):
        actor = JobActor()
        actor.halt()
        self.assertTrue(actor._aborted())
        self.assertFalse(actor._sleep(1.0))

    def test_pause_aborts_clicks(self):
        actor = JobActor()
        actor.set_paused(True)
        self.assertTrue(actor._aborted())
        self.assertFalse(actor.step(None, None, None, ["job"], None, lambda _: None))

    def test_reset_must_open_jobs_again(self):
        actor = JobActor()
        actor._opened_jobs = True
        actor.out_of_energy = True
        actor.reset()
        self.assertFalse(actor._opened_jobs)
        self.assertFalse(actor.out_of_energy)

    def test_recent_click_does_not_spam_do_job(self):
        actor = JobActor()
        actor._last_click = __import__("time").time()
        self.assertFalse(actor.step(None, None, None, ["job"], 50, lambda _: None))

    def test_arm_after_break_allows_job_again(self):
        actor = JobActor()
        actor._wait_cycle = True
        actor._saw_unready = False
        actor.arm_after_break()
        self.assertFalse(actor._wait_cycle)
        self.assertFalse(actor._saw_unready)

    def test_job_list_band_skips_rail_and_do_job(self):
        import numpy as np

        frame = np.zeros((1009, 1920, 3), dtype=np.uint8)
        crop, x1, y1 = job_list_band(frame)
        self.assertGreaterEqual(x1, 300)
        self.assertLess(crop.shape[1], 1200)
        self.assertGreater(y1, 100)


if __name__ == "__main__":
    unittest.main()
