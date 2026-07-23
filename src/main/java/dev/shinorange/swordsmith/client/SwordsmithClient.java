package dev.shinorange.swordsmith.client;

import dev.shinorange.swordsmith.client.render.ForgeBlockEntityRenderer;
import dev.shinorange.swordsmith.client.render.SmithingAnvilBlockEntityRenderer;
import dev.shinorange.swordsmith.client.screen.ForgeScreen;
import dev.shinorange.swordsmith.registry.ModBlockEntities;
import dev.shinorange.swordsmith.registry.ModBlocks;
import dev.shinorange.swordsmith.registry.ModScreenHandlers;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.blockrenderlayer.v1.BlockRenderLayerMap;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.gui.screen.ingame.HandledScreens;
import net.minecraft.client.render.RenderLayer;
import net.minecraft.client.render.block.entity.BlockEntityRendererFactories;

public class SwordsmithClient implements ClientModInitializer {
	@Override
	public void onInitializeClient() {
		BlockEntityRendererFactories.register(ModBlockEntities.FORGE, ForgeBlockEntityRenderer::new);
		BlockEntityRendererFactories.register(ModBlockEntities.SMITHING_ANVIL, SmithingAnvilBlockEntityRenderer::new);
		// The wheel texture has transparent corners.
		BlockRenderLayerMap.INSTANCE.putBlock(ModBlocks.WHETSTONE, RenderLayer.getCutout());
		HandledScreens.register(ModScreenHandlers.FORGE, ForgeScreen::new);
		HudRenderCallback.EVENT.register(HeatHud::render);
	}
}
