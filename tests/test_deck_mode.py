"""Steam Deck mode's game environment (launcher/uncharted_linux.py deck_environment).
Run: python3 -m unittest discover -s tests"""
import sys
import unittest

from paths import ROOT

if str(ROOT / 'launcher') not in sys.path:
    sys.path.insert(0, str(ROOT / 'launcher'))
import uncharted_linux as linux


def environment(**settings):
    """The variables the launcher sets for these settings (the game's own ones first)."""
    env = {'BB_UPSCALER': settings.get('anti_aliasing', 'off'),
           'BB_FRAME_GEN': settings.get('frame_generation', 'off'),
           'BB_FRAME_GEN_MULTIPLIER': settings.get('frame_gen_multiplier', '2')}
    linux.deck_environment(settings, env)
    return env


class DeckModeTests(unittest.TestCase):
    def test_60_by_default_and_30_kept(self):
        self.assertEqual(linux.DECK_SETTINGS['frame_rate'], '60')
        self.assertEqual(environment(steam_deck=True)['BB_VBLANK_HZ'], '60')
        self.assertEqual(environment(steam_deck=True, frame_rate='30')['BB_VBLANK_HZ'], '30')

    def test_rates_above_60_fall_back_to_60(self):
        self.assertEqual(environment(steam_deck=True, frame_rate='144')['BB_VBLANK_HZ'], '60')

    def test_frame_rate_is_not_locked(self):
        self.assertNotIn('frame_rate', linux.DECK_LOCKED)
        self.assertEqual(set(linux.DECK_LOCKED), {'window_size', 'present_mode', 'fullscreen'})

    def test_options_the_deck_cannot_run_are_replaced(self):
        env = environment(steam_deck=True, anti_aliasing='dlss', frame_generation='dlss',
                          frame_gen_multiplier='4')
        self.assertEqual((env['BB_UPSCALER'], env['BB_FRAME_GEN'], env['BB_FRAME_GEN_MULTIPLIER']),
                         ('off', 'off', '2'))
        env = environment(steam_deck=True, anti_aliasing='fsr3', frame_generation='fsr3')
        self.assertEqual((env['BB_UPSCALER'], env['BB_FRAME_GEN']), ('fsr3', 'fsr3'))

    def test_deck_allows(self):
        self.assertTrue(linux.deck_allows('frame_rate', '30'))
        self.assertFalse(linux.deck_allows('frame_rate', '120'))
        self.assertFalse(linux.deck_allows('anti_aliasing', 'fsr4'))
        self.assertTrue(linux.deck_allows('anti_aliasing', 'taa'))
        self.assertTrue(linux.deck_allows('window_size', '1280x800'))

    def test_mode_off_changes_nothing(self):
        env = environment(steam_deck=False, frame_rate='144', anti_aliasing='dlss')
        self.assertNotIn('BB_VBLANK_HZ', env)
        self.assertEqual(env['BB_UPSCALER'], 'dlss')

    def test_readbacks(self):
        self.assertNotIn('BB_READBACKS', environment())
        self.assertNotIn('BB_READBACKS', environment(gpu_readbacks='1'))
        self.assertEqual(environment(gpu_readbacks='0')['BB_READBACKS'], '0')
        self.assertEqual(environment(gpu_readbacks='2', steam_deck=True)['BB_READBACKS'], '2')


if __name__ == '__main__':
    unittest.main()
