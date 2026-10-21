package br.com.japaguimarassi.stevebo;

public enum SteveboMode {
    COMMON("Mundo comum", 0, 0),
    PVP("Arena PvP", 80, 0),
    SURVIVAL("Sobrevivencia", 0, 80),
    BUILD("Construcao", -80, 0),
    EXPLORE("Exploracao", 0, -80);

    public final String label;
    public final int offsetX;
    public final int offsetZ;

    SteveboMode(String label, int offsetX, int offsetZ) {
        this.label = label;
        this.offsetX = offsetX;
        this.offsetZ = offsetZ;
    }

    public static SteveboMode fromLabel(String label) {
        if (label == null) return null;
        for (SteveboMode mode : values()) {
            if (mode.label.equalsIgnoreCase(label.trim())) return mode;
        }
        return null;
    }
}