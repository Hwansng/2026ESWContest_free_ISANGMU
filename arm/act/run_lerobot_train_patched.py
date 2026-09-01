"""Runs lerobot_train with update_last_checkpoint patched to tolerate Windows symlink
permission errors (WinError 1314). Creating a symlink on Windows requires either admin
rights or Developer Mode enabled; neither is guaranteed on this machine, and the
"last" checkpoint pointer is a convenience symlink only -- resume uses an explicit
--config_path, not this link (lerobot/configs/train.py TrainPipelineConfig.__post_init__).
Without this patch, training crashes every `save_freq` steps (2026-08-26, crashed at
step 20000 after a clean 57-minute run).
"""

import logging
import sys

import lerobot.scripts.lerobot_train as lerobot_train_module
from lerobot.utils.train_utils import LAST_CHECKPOINT_LINK


def _patched_update_last_checkpoint(checkpoint_dir):
    last_checkpoint_dir = checkpoint_dir.parent / LAST_CHECKPOINT_LINK
    try:
        if last_checkpoint_dir.is_symlink():
            last_checkpoint_dir.unlink()
        relative_target = checkpoint_dir.relative_to(checkpoint_dir.parent)
        last_checkpoint_dir.symlink_to(relative_target)
    except OSError as exception:
        logging.warning(
            f"Skipping 'last' checkpoint symlink update ({exception}). The checkpoint "
            f"itself was already saved correctly at {checkpoint_dir}; to resume, pass "
            f"--config_path pointing at that checkpoint's pretrained_model/train_config.json."
        )


lerobot_train_module.update_last_checkpoint = _patched_update_last_checkpoint

if __name__ == "__main__":
    sys.argv[0] = "lerobot_train"
    lerobot_train_module.main()
