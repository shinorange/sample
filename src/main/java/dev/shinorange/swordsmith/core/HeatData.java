package dev.shinorange.swordsmith.core;

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.codec.PacketCodecs;

/**
 * Temperature snapshot stored on an item stack: the temperature it had at
 * {@code time} (game time, ticks). The current temperature is derived lazily
 * with Newton's law of cooling, so items keep cooling correctly in chests,
 * on the ground, or on the anvil without ever ticking.
 */
public record HeatData(float temperature, long time) {
	public static final Codec<HeatData> CODEC = RecordCodecBuilder.create(instance -> instance.group(
			Codec.FLOAT.fieldOf("temperature").forGetter(HeatData::temperature),
			Codec.LONG.fieldOf("time").forGetter(HeatData::time)
	).apply(instance, HeatData::new));

	public static final PacketCodec<RegistryByteBuf, HeatData> PACKET_CODEC = PacketCodec.tuple(
			PacketCodecs.FLOAT, HeatData::temperature,
			PacketCodecs.VAR_LONG, HeatData::time,
			HeatData::new
	);
}
