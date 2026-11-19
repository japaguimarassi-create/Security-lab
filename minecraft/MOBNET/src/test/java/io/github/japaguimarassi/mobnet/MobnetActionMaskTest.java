package io.github.japaguimarassi.mobnet;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MobnetActionMaskTest {
    @Test
    void attackIsRejectedWhenMobCannotAttack() {
        assertEquals(MobnetAction.TALK, MobnetActionMask.validate(MobnetAction.ATTACK, false, false, false));
    }

    @Test
    void attackIsRejectedAgainstCreativeAndSpectatorPlayers() {
        assertEquals(MobnetAction.TALK, MobnetActionMask.validate(MobnetAction.ATTACK, true, true, false));
        assertEquals(MobnetAction.TALK, MobnetActionMask.validate(MobnetAction.ATTACK, true, false, true));
    }

    @Test
    void validAttackAndNonAttackActionsArePreserved() {
        assertEquals(MobnetAction.ATTACK, MobnetActionMask.validate(MobnetAction.ATTACK, true, false, false));
        assertEquals(MobnetAction.FOLLOW, MobnetActionMask.validate(MobnetAction.FOLLOW, false, true, true));
    }
}
