package io.github.japaguimarassi.mobnet;

import java.util.UUID;

public record MobnetProfile(UUID mobId, String entityType, String displayName, String personality) {}
