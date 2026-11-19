package io.github.japaguimarassi.mobnet;

public final class MobnetActionMask {
    private MobnetActionMask() {}

    public static MobnetAction validate(MobnetAction action, boolean mobCanAttackPlayer,
                                        boolean playerCreative, boolean playerSpectator) {
        if (action == null) return MobnetAction.TALK;
        if (action == MobnetAction.ATTACK &&
                (!mobCanAttackPlayer || playerCreative || playerSpectator)) {
            return MobnetAction.TALK;
        }
        return action;
    }
}
