// SPDX-FileCopyrightText: 2025 owlmaddie LLC
// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted from CreatureChat; see NOTICE.md.
package io.github.japaguimarassi.mobnet;

import java.util.List;

public class ParsedMessage {
    private final String cleanedMessage;
    private final String originalMessage;
    private final List<Behavior> behaviors;

    public ParsedMessage(String cleanedMessage, String originalMessage, List<Behavior> behaviors) {
        this.cleanedMessage = cleanedMessage;
        this.originalMessage = originalMessage;
        this.behaviors = behaviors;
    }

    public String getCleanedMessage() {
        return cleanedMessage.trim();
    }

    public String getOriginalMessage() {
        return originalMessage.trim();
    }

    public List<Behavior> getBehaviors() {
        return behaviors;
    }
}
