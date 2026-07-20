package dev.shinorange.swordsmith.registry;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.screen.ForgeScreenHandler;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.resource.featuretoggle.FeatureFlags;
import net.minecraft.screen.ScreenHandlerType;

public final class ModScreenHandlers {
	public static final ScreenHandlerType<ForgeScreenHandler> FORGE = Registry.register(
			Registries.SCREEN_HANDLER, Swordsmith.id("forge"),
			new ScreenHandlerType<>(ForgeScreenHandler::new, FeatureFlags.VANILLA_FEATURES));

	public static void init() {
	}

	private ModScreenHandlers() {
	}
}
