// SPDX-FileCopyrightText: 2025 owlmaddie LLC
// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted from CreatureChat; see NOTICE.md.
package io.github.japaguimarassi.mobnet;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class MessageParser {
    private static final Pattern BEHAVIOR_PATTERN = Pattern.compile(
            "[<*](FOLLOW|LEAD|FLEE|ATTACK|PROTECT|FRIENDSHIP|UNFOLLOW|UNLEAD|UNPROTECT|UNFLEE)[:\\s]*(\\s*[+-]?\\d+)?[>*]",
            Pattern.CASE_INSENSITIVE
    );

    private MessageParser() {}

    public static ParsedMessage parseMessage(String input) {
        String source = input == null ? "" : input.trim();
        StringBuilder cleaned = new StringBuilder();
        List<Behavior> behaviors = new ArrayList<>();
        Matcher matcher = BEHAVIOR_PATTERN.matcher(source);

        while (matcher.find()) {
            String behaviorName = matcher.group(1).toUpperCase(java.util.Locale.ROOT);
            Integer argument = matcher.group(2) == null || matcher.group(2).isBlank()
                    ? null : Integer.valueOf(matcher.group(2).trim());
            behaviors.add(new Behavior(behaviorName, argument));
            matcher.appendReplacement(cleaned, "");
        }
        matcher.appendTail(cleaned);

        String display = cleaned.toString().replace("<>", "").replace("**", "").trim();
        return new ParsedMessage(display, source, List.copyOf(behaviors));
    }
}
