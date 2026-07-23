package dev.shinorange.swordsmith.client.render;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;
import dev.shinorange.swordsmith.block.SmithingAnvilBlock;
import dev.shinorange.swordsmith.block.entity.SmithingAnvilBlockEntity;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.client.renderer.texture.OverlayTexture;
import net.minecraft.core.Direction;
import net.minecraft.world.item.ItemDisplayContext;
import net.minecraft.world.item.ItemStack;

/**
 * Draws the workpiece lying flat on the anvil face, and any hilt parts already
 * fitted during final assembly stacked neatly on top of the blade.
 */
public class SmithingAnvilBlockEntityRenderer implements BlockEntityRenderer<SmithingAnvilBlockEntity> {
	public SmithingAnvilBlockEntityRenderer(BlockEntityRendererProvider.Context context) {
	}

	@Override
	public void render(SmithingAnvilBlockEntity entity, float partialTick, PoseStack poseStack, MultiBufferSource buffer, int light, int overlay) {
		ItemStack workpiece = entity.getWorkpiece();
		if (workpiece.isEmpty()) {
			return;
		}
		Direction facing = entity.getBlockState().getValue(SmithingAnvilBlock.FACING);
		float yRot = -facing.toYRot() + 45.0f;

		renderFlat(workpiece, 1.03f, 0.55f, yRot, poseStack, buffer, light, entity);

		int index = 0;
		if (entity.hasGuard()) {
			renderFlat(new ItemStack(ModRegistry.SWORD_GUARD.get()), 1.06f + 0.015f * index++, 0.3f, yRot, poseStack, buffer, light, entity);
		}
		if (entity.hasGrip()) {
			renderFlat(new ItemStack(ModRegistry.SWORD_GRIP.get()), 1.06f + 0.015f * index++, 0.3f, yRot, poseStack, buffer, light, entity);
		}
		if (entity.hasPommel()) {
			renderFlat(new ItemStack(ModRegistry.SWORD_POMMEL.get()), 1.06f + 0.015f * index, 0.3f, yRot, poseStack, buffer, light, entity);
		}
	}

	private void renderFlat(ItemStack stack, float y, float scale, float yRot, PoseStack poseStack,
			MultiBufferSource buffer, int light, SmithingAnvilBlockEntity entity) {
		poseStack.pushPose();
		poseStack.translate(0.5f, y, 0.5f);
		poseStack.mulPose(Axis.YP.rotationDegrees(yRot));
		poseStack.mulPose(Axis.XP.rotationDegrees(90.0f));
		poseStack.scale(scale, scale, scale);
		Minecraft.getInstance().getItemRenderer().renderStatic(stack, ItemDisplayContext.FIXED,
				light, OverlayTexture.NO_OVERLAY, poseStack, buffer, entity.getLevel(), 0);
		poseStack.popPose();
	}
}
