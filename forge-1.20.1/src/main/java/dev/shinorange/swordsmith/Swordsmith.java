package dev.shinorange.swordsmith;

import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

/**
 * Real Swordsmithing, Forge 1.20.1 edition. Same smithy as the Fabric build:
 * smelt a bloom, hammer at forging heat, quench, temper, grind, fit the hilt —
 * and the finished sword is only as good as the hands that made it.
 */
@Mod(Swordsmith.MOD_ID)
public class Swordsmith {
	public static final String MOD_ID = "swordsmith";

	public Swordsmith() {
		IEventBus modBus = FMLJavaModLoadingContext.get().getModEventBus();
		ModRegistry.register(modBus);
	}

	public static ResourceLocation id(String path) {
		return new ResourceLocation(MOD_ID, path);
	}
}
