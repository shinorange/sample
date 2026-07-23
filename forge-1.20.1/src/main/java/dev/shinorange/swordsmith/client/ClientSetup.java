package dev.shinorange.swordsmith.client;

import dev.shinorange.swordsmith.Swordsmith;
import dev.shinorange.swordsmith.client.render.ForgeBlockEntityRenderer;
import dev.shinorange.swordsmith.client.render.SmithingAnvilBlockEntityRenderer;
import dev.shinorange.swordsmith.client.screen.ForgeScreen;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.client.gui.screens.MenuScreens;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.EntityRenderersEvent;
import net.minecraftforge.client.event.RegisterGuiOverlaysEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;

@Mod.EventBusSubscriber(modid = Swordsmith.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public final class ClientSetup {
	@SubscribeEvent
	public static void onClientSetup(FMLClientSetupEvent event) {
		event.enqueueWork(() -> MenuScreens.register(ModRegistry.FORGE_MENU.get(), ForgeScreen::new));
	}

	@SubscribeEvent
	public static void onRegisterRenderers(EntityRenderersEvent.RegisterRenderers event) {
		event.registerBlockEntityRenderer(ModRegistry.FORGE_BE.get(), ForgeBlockEntityRenderer::new);
		event.registerBlockEntityRenderer(ModRegistry.SMITHING_ANVIL_BE.get(), SmithingAnvilBlockEntityRenderer::new);
	}

	@SubscribeEvent
	public static void onRegisterOverlays(RegisterGuiOverlaysEvent event) {
		event.registerAboveAll("heat", HeatHud::render);
	}

	private ClientSetup() {
	}
}
