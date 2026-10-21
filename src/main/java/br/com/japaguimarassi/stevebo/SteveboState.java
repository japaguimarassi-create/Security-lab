package br.com.japaguimarassi.stevebo;

public final class SteveboState {
    private static boolean creationRequested;
    private static SteveboMode selectedMode = SteveboMode.COMMON;

    private SteveboState() {
    }

    public static synchronized void requestWorldCreation(SteveboMode mode) {
        selectedMode = mode == null ? SteveboMode.COMMON : mode;
        creationRequested = true;
    }

    public static synchronized SteveboMode consumeWorldCreationRequest() {
        if (!creationRequested) return null;
        creationRequested = false;
        return selectedMode;
    }

    public static synchronized void cancelWorldCreation() {
        creationRequested = false;
    }
}