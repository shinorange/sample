package dev.shinorange.swordsmith.registry;

import com.mojang.serialization.Codec;
import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.core.HeatData;
import dev.shinorange.swordsmith.core.QualityData;
import net.minecraft.component.ComponentType;
import net.minecraft.network.codec.PacketCodecs;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;

public final class ModComponents {
	public static final ComponentType<HeatData> HEAT = Registry.register(
			Registries.DATA_COMPONENT_TYPE, Swordsmith.id("heat"),
			ComponentType.<HeatData>builder().codec(HeatData.CODEC).packetCodec(HeatData.PACKET_CODEC).build());

	public static final ComponentType<Integer> GRIND_PROGRESS = Registry.register(
			Registries.DATA_COMPONENT_TYPE, Swordsmith.id("grind_progress"),
			ComponentType.<Integer>builder().codec(Codec.intRange(0, 1024)).packetCodec(PacketCodecs.VAR_INT).build());

	public static final ComponentType<QualityData> QUALITY = Registry.register(
			Registries.DATA_COMPONENT_TYPE, Swordsmith.id("quality"),
			ComponentType.<QualityData>builder().codec(QualityData.CODEC).packetCodec(QualityData.PACKET_CODEC).build());

	public static final ComponentType<Float> SWORD_QUALITY = Registry.register(
			Registries.DATA_COMPONENT_TYPE, Swordsmith.id("sword_quality"),
			ComponentType.<Float>builder().codec(Codec.floatRange(0f, 1f)).packetCodec(PacketCodecs.FLOAT).build());

	public static void init() {
	}

	private ModComponents() {
	}
}
