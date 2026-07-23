package dev.shinorange.swordsmith.core;

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.util.math.MathHelper;

/**
 * Running record of how well a blade has been worked: the sum and count of
 * per-strike scores on the anvil, and the quench accuracy. It rides on the
 * workpiece as a component through every stage, and at hilt assembly it
 * collapses into the sword's final craftsmanship.
 */
public record QualityData(float strikeScoreSum, int strikes, float quenchScore) {
	public static final QualityData EMPTY = new QualityData(0f, 0, 0f);

	public static final Codec<QualityData> CODEC = RecordCodecBuilder.create(instance -> instance.group(
			Codec.FLOAT.fieldOf("strike_score_sum").forGetter(QualityData::strikeScoreSum),
			Codec.INT.fieldOf("strikes").forGetter(QualityData::strikes),
			Codec.FLOAT.fieldOf("quench_score").forGetter(QualityData::quenchScore)
	).apply(instance, QualityData::new));

	public static final PacketCodec<RegistryByteBuf, QualityData> PACKET_CODEC = PacketCodec.tuple(
			PacketCodecs.FLOAT, QualityData::strikeScoreSum,
			PacketCodecs.VAR_INT, QualityData::strikes,
			PacketCodecs.FLOAT, QualityData::quenchScore,
			QualityData::new
	);

	public QualityData addStrike(float score) {
		return new QualityData(strikeScoreSum + score, strikes + 1, quenchScore);
	}

	public QualityData withQuench(float score) {
		return new QualityData(strikeScoreSum, strikes, score);
	}

	public float strikeAverage() {
		return strikes == 0 ? 0.75f : strikeScoreSum / strikes;
	}

	/** 65% hammer work, 35% quench accuracy. */
	public float finalQuality() {
		float quench = quenchScore <= 0f ? 0.6f : quenchScore;
		return MathHelper.clamp(0.65f * strikeAverage() + 0.35f * quench, 0f, 1f);
	}
}
