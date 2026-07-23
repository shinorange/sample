package dev.shinorange.swordsmith.client.render;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;
import dev.shinorange.swordsmith.block.ForgeBlock;
import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.LightTexture;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.client.renderer.texture.OverlayTexture;
import net.minecraft.world.item.ItemDisplayContext;
import net.minecraft.world.item.ItemStack;

/** Draws the workpiece lying in the coals, full-bright while the fire is lit. */
public class ForgeBlockEntityRenderer implements BlockEntityRenderer<ForgeBlockEntity> {
	public ForgeBlockEntityRenderer(BlockEntityRendererProvider.Context context) {
	}

	@Override
	public void render(ForgeBlockEntity entity, float partialTick, PoseStack poseStack, MultiBufferSource buffer, int light, int overlay) {
		ItemStack workpiece = entity.getWorkpiece();
		if (workpiece.isEmpty()) {
			return;
		}
		poseStack.pushPose();
		poseStack.translate(0.5f, 1.03f, 0.5f);
		poseStack.mulPose(Axis.YP.rotationDegrees(45.0f));
		poseStack.mulPose(Axis.XP.rotationDegrees(90.0f));
		poseStack.scale(0.55f, 0.55f, 0.55f);
		boolean lit = entity.getBlockState().getValue(ForgeBlock.LIT);
		int itemLight = lit ? LightTexture.FULL_BRIGHT : light;
		Minecraft.getInstance().getItemRenderer().renderStatic(workpiece, ItemDisplayContext.FIXED,
				itemLight, OverlayTexture.NO_OVERLAY, poseStack, buffer, entity.getLevel(), 0);
		poseStack.popPose();
	}
}
