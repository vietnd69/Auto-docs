import os
import shutil
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).parents[2]
SCRIPTS_DIR = str(_WORKSPACE_ROOT / "dst-scripts" / "prefabs")

# File maps
f_added = os.path.join(SCRIPTS_DIR, "new_test_prefab.lua")
f_mod = os.path.join(SCRIPTS_DIR, "abigail.lua")
f_mod_backup = os.path.join(SCRIPTS_DIR, "abigail.lua.bak")
f_del = os.path.join(SCRIPTS_DIR, "yots_worm_lantern.lua")
f_del_backup = os.path.join(SCRIPTS_DIR, "yots_worm_lantern.lua.bak")

f_moved_false = os.path.join(SCRIPTS_DIR, "yotr_token.lua")
f_moved_false_dst = os.path.join(SCRIPTS_DIR, "yotr_token_moved.lua")

f_moved_true = os.path.join(SCRIPTS_DIR, "yotr_rabbitshrine.lua")
f_moved_true_backup = os.path.join(SCRIPTS_DIR, "yotr_rabbitshrine.lua.bak")
f_moved_true_dst = os.path.join(SCRIPTS_DIR, "yotr_rabbitshrine_moved.lua")

def apply_simulations():
    # 1. ADDED
    with open(f_added, "w") as f:
        f.write('print("This is a new test prefab")\n')

    # 2. MODIFIED
    shutil.copy2(f_mod, f_mod_backup)
    with open(f_mod, "a") as f:
        f.write('\nprint("abigail modified")\n')

    # 3. DELETED
    shutil.move(f_del, f_del_backup)

    # 4. MOVED (false)
    shutil.move(f_moved_false, f_moved_false_dst)

    # 5. MOVED (true)
    shutil.copy2(f_moved_true, f_moved_true_backup) # Keep backup in place to restore later, but we move the real one
    shutil.move(f_moved_true, f_moved_true_dst)
    with open(f_moved_true_dst, "a") as f:
        f.write('\nprint("shrine moved and modified")\n')

    print("Simulated changes applied.")

def revert_simulations():
    import os
    if os.path.exists(f_added): os.remove(f_added)

    if os.path.exists(f_mod_backup):
        shutil.move(f_mod_backup, f_mod)

    if os.path.exists(f_del_backup):
        shutil.move(f_del_backup, f_del)

    if os.path.exists(f_moved_false_dst):
        shutil.move(f_moved_false_dst, f_moved_false)

    if os.path.exists(f_moved_true_dst):
        os.remove(f_moved_true_dst)
    if os.path.exists(f_moved_true_backup):
        shutil.move(f_moved_true_backup, f_moved_true)

    print("Simulated changes reverted.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        revert_simulations()
    else:
        apply_simulations()
