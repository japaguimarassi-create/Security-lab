(() => {
  const payload = window.KODEX_MLM_DATA;
  const unavailable = {
    ready: false,
    metadata: null,
    generate: () => ""
  };
  if (!payload || payload.parameterCount !== 264192) {
    window.KodexMobileMLM = unavailable;
    return;
  }

  function decodeTensor(encoded) {
    const binary = atob(encoded.data);
    const output = new Float32Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      const byte = binary.charCodeAt(index);
      output[index] = (byte > 127 ? byte - 256 : byte) * encoded.scale;
    }
    return output;
  }

  const tensors = Object.fromEntries(
    Object.entries(payload.tensors).map(([name, tensor]) => [name, decodeTensor(tensor)])
  );
  const merges = payload.merges;
  const tokenBytes = Array.from({ length: 256 }, (_, index) => Uint8Array.of(index));
  for (const [left, right] of merges) {
    const a = tokenBytes[left];
    const b = tokenBytes[right];
    const joined = new Uint8Array(a.length + b.length);
    joined.set(a);
    joined.set(b, a.length);
    tokenBytes.push(joined);
  }
  const decoder = new TextDecoder("utf-8");
  const encoder = new TextEncoder();

  function mergePair(sequence, left, right, newId) {
    const merged = [];
    for (let index = 0; index < sequence.length;) {
      if (index + 1 < sequence.length && sequence[index] === left && sequence[index + 1] === right) {
        merged.push(newId);
        index += 2;
      } else {
        merged.push(sequence[index]);
        index += 1;
      }
    }
    return merged;
  }

  function encode(text) {
    let sequence = Array.from(encoder.encode(text));
    for (let index = 0; index < merges.length; index += 1) {
      const [left, right] = merges[index];
      sequence = mergePair(sequence, left, right, 256 + index);
    }
    return sequence;
  }

  function decode(tokenIds) {
    let totalLength = 0;
    for (const tokenId of tokenIds) totalLength += tokenBytes[tokenId].length;
    const bytes = new Uint8Array(totalLength);
    let offset = 0;
    for (const tokenId of tokenIds) {
      const part = tokenBytes[tokenId];
      bytes.set(part, offset);
      offset += part.length;
    }
    return decoder.decode(bytes);
  }

  function layerNorm(input, weight, bias) {
    let mean = 0;
    for (let index = 0; index < input.length; index += 1) mean += input[index];
    mean /= input.length;
    let variance = 0;
    for (let index = 0; index < input.length; index += 1) {
      const delta = input[index] - mean;
      variance += delta * delta;
    }
    variance /= input.length;
    const inverse = 1 / Math.sqrt(variance + 1e-5);
    const output = new Float32Array(input.length);
    for (let index = 0; index < input.length; index += 1) {
      output[index] = (input[index] - mean) * inverse * weight[index] + bias[index];
    }
    return output;
  }

  function sigmoid(value) {
    const limited = Math.max(-18, Math.min(18, value));
    return 1 / (1 + Math.exp(-limited));
  }

  function modelStep(tokenId, hidden, cell) {
    const embedding = tensors["embedding.weight"];
    const embedded = new Float32Array(128);
    const base = tokenId * 128;
    for (let index = 0; index < 128; index += 1) embedded[index] = embedding[base + index];
    const input = layerNorm(embedded, tensors["input_norm.weight"], tensors["input_norm.bias"]);
    const weightInput = tensors["lstm.weight_ih_l0"];
    const weightHidden = tensors["lstm.weight_hh_l0"];
    const biasInput = tensors["lstm.bias_ih_l0"];
    const biasHidden = tensors["lstm.bias_hh_l0"];
    const gates = new Float32Array(512);
    for (let output = 0; output < 512; output += 1) {
      let sum = biasInput[output] + biasHidden[output];
      const inputBase = output * 128;
      for (let index = 0; index < 128; index += 1) {
        sum += weightInput[inputBase + index] * input[index];
        sum += weightHidden[inputBase + index] * hidden[index];
      }
      gates[output] = sum;
    }

    const nextHidden = new Float32Array(128);
    const nextCell = new Float32Array(128);
    for (let index = 0; index < 128; index += 1) {
      const inputGate = sigmoid(gates[index]);
      const forgetGate = sigmoid(gates[128 + index]);
      const candidate = Math.tanh(gates[256 + index]);
      const outputGate = sigmoid(gates[384 + index]);
      const value = forgetGate * cell[index] + inputGate * candidate;
      nextCell[index] = value;
      nextHidden[index] = outputGate * Math.tanh(value);
    }

    const normalized = layerNorm(nextHidden, tensors["output_norm.weight"], tensors["output_norm.bias"]);
    const outputWeight = tensors["lm_head.weight"];
    const outputBias = tensors["lm_head.bias"];
    const logits = new Float32Array(512);
    for (let output = 0; output < 512; output += 1) {
      let sum = outputBias[output];
      const outputBase = output * 128;
      for (let index = 0; index < 128; index += 1) {
        sum += outputWeight[outputBase + index] * normalized[index];
      }
      logits[output] = sum;
    }
    return { hidden: nextHidden, cell: nextCell, logits };
  }

  function sampleToken(logits, temperature, topK, random) {
    const candidates = [];
    for (let index = 0; index < logits.length; index += 1) {
      candidates.push({ id: index, score: logits[index] / temperature });
    }
    candidates.sort((left, right) => right.score - left.score);
    const selected = candidates.slice(0, Math.max(1, topK));
    const maxScore = selected[0].score;
    let total = 0;
    for (const item of selected) {
      item.probability = Math.exp(item.score - maxScore);
      total += item.probability;
    }
    let threshold = random() * total;
    for (const item of selected) {
      threshold -= item.probability;
      if (threshold <= 0) return item.id;
    }
    return selected[0].id;
  }

  function generate(text, mode = "chat", options = {}) {
    const clean = String(text ?? "").trim();
    if (!clean) return "";
    const context = "Modo: " + (mode === "build" ? "build" : "chat") +
      "\nUsuário: " + clean + "\nKodex: ";
    let inputIds = encode(context);
    const maxContext = payload.maxContextTokens || 144;
    if (inputIds.length > maxContext) inputIds = inputIds.slice(-maxContext);
    let hidden = new Float32Array(128);
    let cell = new Float32Array(128);
    let state = null;
    for (const tokenId of inputIds) {
      state = modelStep(tokenId, hidden, cell);
      hidden = state.hidden;
      cell = state.cell;
    }
    let logits = state ? state.logits : new Float32Array(512);
    const generated = [];
    const maxNewTokens = Math.max(8, Math.min(160, Number(options.maxNewTokens) || 104));
    const temperature = Math.max(0.25, Math.min(1.3, Number(options.temperature) || 0.72));
    const topK = Math.max(1, Math.min(12, Number(options.topK) || 6));
    let randomState = ((clean.length * 2654435761) ^ (inputIds.length * 2246822519)) >>> 0;
    const random = () => {
      randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0;
      return randomState / 4294967296;
    };
    for (let step = 0; step < maxNewTokens; step += 1) {
      const next = sampleToken(logits, temperature, topK, random);
      generated.push(next);
      const partial = decode(generated);
      if (partial.includes("<fim>")) break;
      if (partial.includes("\nUsuário:") || partial.includes("\nModo:")) break;
      state = modelStep(next, hidden, cell);
      hidden = state.hidden;
      cell = state.cell;
      logits = state.logits;
    }
    return decode(generated)
      .split("<fim>")[0]
      .split("\nUsuário:")[0]
      .split("\nModo:")[0]
      .trim();
  }

  window.KodexMobileMLM = {
    ready: true,
    metadata: {
      version: payload.version,
      architecture: payload.architecture,
      parameterCount: payload.parameterCount,
      training: payload.training
    },
    generate
  };
})();
