package dev.shinorange.swordsmith.client.render;

import dev.shinorange.swordsmith.block.SmithingAnvilBlock;
import dev.shinorange.swordsmith.block.entity.SmithingAnvilBlockEntity;
import dev.shinorange.swordsmith.registry.ModItems;
import net.minecraft.client.render.OverlayTexture;
import net.minecraft.client.render.VertexConsumerProvider;
import net.minecraft.client.render.block.entity.BlockEntityRenderer;
import net.minecraft.client.render.block.entity.BlockEntityRendererFactory;
import net.minecraft.client.render.item.ItemRenderer;
import net.minecraft.client.render.model.json.ModelTransformationMode;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.item.ItemStack;
import net.minecraft.util.math.Direction;
import net.minecraft.util.math.RotationAxis;

/**
 * Draws the workpiece lying flat on the anvil face, and any hilt parts already
 * fitted during final assembly stacked neatly on top of the blade.
 */
public class SmithingAnvilBlockEntityRenderer implements BlockEntityRenderer<SmithingAnvilBlockEntity> {
	private final ItemRenderer itemRenderer;

	public SmithingAnvilBlockEntityRenderer(BlockEntityRendererFactory.Context context) {
		this.itemRenderer = context.getItemRenderer();
	}

	@Override
	public void render(SmithingAnvilBlockEntity entity, float tickDelta, MatrixStack matrices, VertexConsumerProvider vertexConsumers, int light, int overlay) {
		ItemStack workpiece = entity.getWorkpiece();
		if (workpiece.isEmpty()) {
			return;
		}
		Direction facing = entity.getCachedState().get(SmithingAnvilBlock.FACING);
		float yRot = -facing.asRotation() + 45.0f;

		renderFlat(workpiece, 1.03f, 0.55f, yRot, matrices, vertexConsumers, light, entity);

		int index = 0;
		if (entity.hasGuard()) {
			renderFlat(new ItemStack(ModItems.SWORD_GUARD), 1.06f + 0.015f * index++, 0.3f, yRot, matrices, vertexConsumers, light, entity);
		}
		if (entity.hasGrip()) {
			renderFlat(new ItemStack(ModItems.SWORD_GRIP), 1.06f + 0.015f * index++, 0.3f, yRot, matrices, vertexConsumers, light, entity);
		}
		if (entity.hasPommel()) {
			renderFlat(new ItemStack(ModItems.SWORD_POMMEL), 1.06f + 0.015f * index, 0.3f, yRot, matrices, vertexConsumers, light, entity);
		}
	}

	private void renderFlat(ItemStack stack, float y, float scale, float yRot, MatrixStack matrices,
			VertexConsumerProvider vertexConsumers, int light, SmithingAnvilBlockEntity entity) {
		matrices.push();
		matrices.translate(0.5f, y, 0.5f);
		matrices.multiply(RotationAxis.POSITIVE_Y.rotationDegrees(yRot));
		matrices.multiply(RotationAxis.POSITIVE_X.rotationDegrees(90.0f));
		matrices.scale(scale, scale, scale);
		itemRenderer.renderItem(stack, ModelTransformationMode.FIXED, light, OverlayTexture.DEFAULT_UV,
				matrices, vertexConsumers, entity.getWorld(), 0);
		matrices.pop();
	}
}
