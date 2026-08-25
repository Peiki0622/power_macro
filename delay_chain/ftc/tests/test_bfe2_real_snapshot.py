"""Static B-FE2.2 real-close deck test without HSPICE."""
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import bfe2_real_snapshot as snap  # noqa
import bfe2_latch_load as load  # noqa
class TestSnapshot(unittest.TestCase):
 def test_close_is_finite_and_common(self):
  cells=json.loads((ROOT/"discovery"/"selected_cells.json").read_text()); deck=snap.render(cells,load.SCENARIOS[0],400.0);snap.validate(deck);self.assertEqual(deck.count("XLATCH_"),30);self.assertIn("V_LATCH_G latch_g vss_a PWL",deck);self.assertNotIn("DFFRPQ",deck)
if __name__=="__main__":unittest.main()
