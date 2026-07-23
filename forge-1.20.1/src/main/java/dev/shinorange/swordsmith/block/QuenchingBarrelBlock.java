package dev.shinorange.swordsmith.block;

import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.ItemUtils;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.phys.BlockHitResult;

/**
 * The quenching tub: plunge a rough blade at 780-950 C to harden it (865 C is
 * the master's mark), hotter and it cracks, cooler and nothing takes. Any
 * other glowing workpiece can be dunked simply to cool it.
 */
public class QuenchingBarrelBlock extends Block {
	public static final BooleanProperty FILLED = BooleanProperty.create("filled");

	public QuenchingBarrelBlock(Properties properties) {
		super(properties);
		this.registerDefaultState(this.stateDefinition.any().setValue(FILLED, false));
	}

	@Override
	protected void createBlockStateDefinition(StateDefinition.Builder<Block, BlockState> builder) {
		builder.add(FILLED);
	}

	@Override
	public InteractionResult use(BlockState state, Level level, BlockPos pos, Player player, InteractionHand hand, BlockHitResult hit) {
		ItemStack stack = player.getItemInHand(hand);
		boolean filled = state.getValue(FILLED);

		if (stack.is(Items.WATER_BUCKET)) {
			if (level.isClientSide) {
				return InteractionResult.SUCCESS;
			}
			if (!filled) {
				level.setBlock(pos, state.setValue(FILLED, true), Block.UPDATE_ALL);
				player.setItemInHand(hand, ItemUtils.createFilledResult(stack, player, new ItemStack(Items.BUCKET)));
				level.playSound(null, pos, SoundEvents.BUCKET_EMPTY, SoundSource.BLOCKS, 1.0f, 1.0f);
			} else {
				player.displayClientMessage(Component.translatable("msg.swordsmith.barrel_full"), true);
			}
			return InteractionResult.CONSUME;
		}

		if (!Smithing.isHeatable(stack)) {
			return InteractionResult.PASS;
		}

		if (!filled) {
			if (!level.isClientSide) {
				player.displayClientMessage(Component.translatable("msg.swordsmith.barrel_empty"), true);
			}
			return InteractionResult.sidedSuccess(level.isClientSide);
		}

		if (level.isClientSide) {
			return InteractionResult.SUCCESS;
		}

		float temp = Heat.current(level, stack);

		// The hardening quench itself.
		if (stack.is(ModRegistry.ROUGH_BLADE.get())) {
			if (temp >= Heat.QUENCH_MIN && temp <= Heat.QUENCH_MAX) {
				ItemStack quenched = new ItemStack(ModRegistry.QUENCHED_BLADE.get());
				Quality.carry(stack, quenched);
				Quality.setQuench(quenched, Quality.quenchScore(temp));
				player.setItemInHand(hand, quenched);
				player.displayClientMessage(Component.translatable("msg.swordsmith.quench_ok"), true);
				hiss(level, pos, 1.0f);
			} else if (temp > Heat.QUENCH_MAX) {
				ItemStack cracked = new ItemStack(ModRegistry.CRACKED_BLADE.get());
				Quality.carry(stack, cracked);
				player.setItemInHand(hand, cracked);
				player.displayClientMessage(Component.translatable("msg.swordsmith.quench_crack"), true);
				level.playSound(null, pos, SoundEvents.ITEM_BREAK, SoundSource.BLOCKS, 1.0f, 0.8f);
				hiss(level, pos, 1.0f);
			} else if (temp > Heat.COLD_WORK_MAX) {
				Heat.set(level, stack, Heat.AMBIENT);
				player.displayClientMessage(Component.translatable("msg.swordsmith.quench_weak"), true);
				hiss(level, pos, 0.6f);
			} else {
				player.displayClientMessage(Component.translatable("msg.swordsmith.quench_cold"), true);
			}
			return InteractionResult.CONSUME;
		}

		// Anything else just gets cooled off.
		if (temp > Heat.COLD_WORK_MAX) {
			Heat.set(level, stack, Heat.AMBIENT);
			hiss(level, pos, 0.7f);
		}
		return InteractionResult.CONSUME;
	}

	private void hiss(Level level, BlockPos pos, float volume) {
		level.playSound(null, pos, SoundEvents.LAVA_EXTINGUISH, SoundSource.BLOCKS, volume, 1.0f);
		if (level instanceof ServerLevel serverLevel) {
			serverLevel.sendParticles(ParticleTypes.CLOUD,
					pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 10, 0.2, 0.1, 0.2, 0.02);
			serverLevel.sendParticles(ParticleTypes.SPLASH,
					pos.getX() + 0.5, pos.getY() + 1.0, pos.getZ() + 0.5, 8, 0.25, 0.05, 0.25, 0.1);
		}
	}
}
