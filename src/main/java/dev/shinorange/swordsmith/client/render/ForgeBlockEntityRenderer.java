package dev.shinorange.swordsmith.client.render;

import dev.shinorange.swordsmith.block.ForgeBlock;
import dev.shinorange.swordsmith.block.entity.ForgeBlockEntity;
import net.minecraft.client.render.LightmapTextureManager;
import net.minecraft.client.render.OverlayTexture;
import net.minecraft.client.render.VertexConsumerProvider;
import net.minecraft.client.render.block.entity.BlockEntityRenderer;
import net.minecraft.client.render.block.entity.BlockEntityRendererFactory;
import net.minecraft.client.render.item.ItemRenderer;
import net.minecraft.client.render.model.json.ModelTransformationMode;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.item.ItemStack;
import net.minecraft.util.math.RotationAxis;

/** Draws the workpiece lying in the coals, full-bright while the fire is lit. */
public class ForgeBlockEntityRenderer implements BlockEntityRenderer<ForgeBlockEntity> {
	private final ItemRenderer itemRenderer;

	public ForgeBlockEntityRenderer(BlockEntityRendererFactory.Context context) {
		this.itemRenderer = context.getItemRenderer();
	}

	@Override
	public void render(ForgeBlockEntity entity, float tickDelta, MatrixStack matrices, VertexConsumerProvider vertexConsumers, int light, int overlay) {
		ItemStack workpiece = entity.getWorkpiece();
		if (workpiece.isEmpty()) {
			return;
		}
		matrices.push();
		matrices.translate(0.5f, 1.03f, 0.5f);
		matrices.multiply(RotationAxis.POSITIVE_Y.rotationDegrees(45.0f));
		matrices.multiply(RotationAxis.POSITIVE_X.rotationDegrees(90.0f));
		matrices.scale(0.55f, 0.55f, 0.55f);
		boolean lit = entity.getCachedState().get(ForgeBlock.LIT);
		int itemLight = lit ? LightmapTextureManager.MAX_LIGHT_COORDINATE : light;
		itemRenderer.renderItem(workpiece, ModelTransformationMode.FIXED, itemLight, OverlayTexture.DEFAULT_UV,
				matrices, vertexConsumers, entity.getWorld(), 0);
		matrices.pop();
	}
}
