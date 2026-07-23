package dev.shinorange.swordsmith.block.entity;

import dev.shinorange.swordsmith.block.ForgeBlock;
import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.menu.ForgeMenu;
import dev.shinorange.swordsmith.registry.ModRegistry;
import net.minecraft.core.BlockPos;
import net.minecraft.core.NonNullList;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.Packet;
import net.minecraft.network.protocol.game.ClientGamePacketListener;
import net.minecraft.network.protocol.game.ClientboundBlockEntityDataPacket;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.Container;
import net.minecraft.world.ContainerHelper;
import net.minecraft.world.MenuProvider;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerData;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

/**
 * The fire simulation, NBT edition. Slot 0 holds the workpiece (rendered
 * in-world), slot 1 stockpiles fuel that feeds the fire one piece at a time.
 * A lit fire without blast banks at ~300 C (perfect for tempering); bellows
 * air pushes it toward 1280 C for forging heat and bloomery smelting. Any
 * hardened blade that climbs past 460 C anneals back to a rough blade.
 */
public class ForgeBlockEntity extends BlockEntity implements Container, MenuProvider {
	public static final int SLOT_WORKPIECE = 0;
	public static final int SLOT_FUEL = 1;
	public static final int SLOT_COUNT = 2;

	public static final int PROPERTY_FIRE_TEMP = 0;
	public static final int PROPERTY_WORK_TEMP = 1;
	public static final int PROPERTY_FUEL_SECONDS = 2;
	public static final int PROPERTY_AIRFLOW = 3;
	public static final int PROPERTY_PROGRESS = 4;
	public static final int PROPERTY_COUNT = 5;

	private static final float MAX_FUEL_SECONDS = 300f;
	private static final float FUEL_SECONDS_PER_COAL = 60f;

	private final NonNullList<ItemStack> items = NonNullList.withSize(SLOT_COUNT, ItemStack.EMPTY);
	private float fuelSeconds;
	private float airflow;
	private float forgeTemp = Heat.AMBIENT;
	private float workTemp = Heat.AMBIENT;
	private int smeltProgress;
	private int temperProgress;

	private final ContainerData dataAccess = new ContainerData() {
		@Override
		public int get(int index) {
			return switch (index) {
				case PROPERTY_FIRE_TEMP -> (int) forgeTemp;
				case PROPERTY_WORK_TEMP -> (int) workTemp;
				case PROPERTY_FUEL_SECONDS -> (int) fuelSeconds;
				case PROPERTY_AIRFLOW -> (int) (airflow * 100f);
				case PROPERTY_PROGRESS -> progressPercent();
				default -> 0;
			};
		}

		@Override
		public void set(int index, int value) {
		}

		@Override
		public int getCount() {
			return PROPERTY_COUNT;
		}
	};

	public ForgeBlockEntity(BlockPos pos, BlockState state) {
		super(ModRegistry.FORGE_BE.get(), pos, state);
	}

	private int progressPercent() {
		if (smeltProgress > 0) {
			return Math.min(100, smeltProgress * 100 / Heat.SMELT_TICKS);
		}
		if (temperProgress > 0) {
			return Math.min(100, temperProgress * 100 / Heat.TEMPER_TICKS);
		}
		return 0;
	}

	public static void serverTick(Level level, BlockPos pos, BlockState state, ForgeBlockEntity forge) {
		boolean lit = state.getValue(ForgeBlock.LIT);
		float target = lit ? Heat.FORGE_BASE_TEMP + forge.airflow * Heat.BELLOWS_BONUS : Heat.AMBIENT;
		forge.forgeTemp += (target - forge.forgeTemp) * 0.005f;
		forge.airflow = Math.max(0f, forge.airflow - 1f / 600f);

		if (lit) {
			if (forge.fuelSeconds <= MAX_FUEL_SECONDS - FUEL_SECONDS_PER_COAL) {
				ItemStack fuel = forge.items.get(SLOT_FUEL);
				if (!fuel.isEmpty()) {
					fuel.shrink(1);
					forge.fuelSeconds += FUEL_SECONDS_PER_COAL;
					forge.setChanged();
				}
			}
			forge.fuelSeconds -= (1f + forge.airflow) / 20f;
			if (forge.fuelSeconds <= 0f) {
				forge.fuelSeconds = 0f;
				level.setBlock(pos, state.setValue(ForgeBlock.LIT, false), Block.UPDATE_ALL);
			}
		}

		ItemStack workpiece = forge.items.get(SLOT_WORKPIECE);
		if (!workpiece.isEmpty()) {
			forge.workTemp += (forge.forgeTemp - forge.workTemp) * 0.02f;
			forge.tickTransformations(level, pos);
		} else {
			forge.workTemp = forge.forgeTemp;
		}

		if (level.getGameTime() % 20 == 0) {
			forge.setChanged();
		}
	}

	private void tickTransformations(Level level, BlockPos pos) {
		ItemStack workpiece = items.get(SLOT_WORKPIECE);
		if (workpiece.is(Items.RAW_IRON)) {
			if (workTemp >= Heat.SMELT_TEMP) {
				if (++smeltProgress >= Heat.SMELT_TICKS) {
					replaceWorkpiece(new ItemStack(ModRegistry.IRON_BLOOM.get()));
					smeltProgress = 0;
					level.playSound(null, pos, SoundEvents.LAVA_POP, SoundSource.BLOCKS, 1.0f, 0.8f);
					if (level instanceof ServerLevel serverLevel) {
						serverLevel.sendParticles(ParticleTypes.LAVA,
								pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 8, 0.2, 0.1, 0.2, 0.0);
					}
				}
			} else if (smeltProgress > 0 && workTemp < 700f) {
				smeltProgress--;
			}
		} else if (isHardenedBlade() && workTemp > Heat.ANNEAL_TEMP) {
			replaceWorkpiece(new ItemStack(ModRegistry.ROUGH_BLADE.get()));
			temperProgress = 0;
			level.playSound(null, pos, SoundEvents.FIRE_EXTINGUISH, SoundSource.BLOCKS, 0.8f, 0.5f);
			if (level instanceof ServerLevel serverLevel) {
				serverLevel.sendParticles(ParticleTypes.SMOKE,
						pos.getX() + 0.5, pos.getY() + 1.2, pos.getZ() + 0.5, 12, 0.2, 0.1, 0.2, 0.02);
			}
		} else if (workpiece.is(ModRegistry.QUENCHED_BLADE.get())) {
			if (workTemp >= Heat.TEMPER_MIN && workTemp <= Heat.TEMPER_MAX) {
				if (++temperProgress >= Heat.TEMPER_TICKS) {
					replaceWorkpiece(new ItemStack(ModRegistry.TEMPERED_BLADE.get()));
					temperProgress = 0;
					level.playSound(null, pos, SoundEvents.EXPERIENCE_ORB_PICKUP, SoundSource.BLOCKS, 0.7f, 1.2f);
				}
			}
		}
	}

	private boolean isHardenedBlade() {
		ItemStack workpiece = items.get(SLOT_WORKPIECE);
		return workpiece.is(ModRegistry.QUENCHED_BLADE.get())
				|| workpiece.is(ModRegistry.TEMPERED_BLADE.get())
				|| workpiece.is(ModRegistry.SHARP_BLADE.get());
	}

	private void replaceWorkpiece(ItemStack stack) {
		Quality.carry(items.get(SLOT_WORKPIECE), stack);
		items.set(SLOT_WORKPIECE, stack);
		setChangedAndSync();
	}

	public boolean addFuelItem(ItemStack held) {
		ItemStack current = items.get(SLOT_FUEL);
		if (current.isEmpty()) {
			items.set(SLOT_FUEL, held.copyWithCount(1));
			setChanged();
			return true;
		}
		if (current.is(held.getItem()) && current.getCount() < current.getMaxStackSize()) {
			current.grow(1);
			setChanged();
			return true;
		}
		return false;
	}

	public boolean hasFuel() {
		return fuelSeconds > 0f || !items.get(SLOT_FUEL).isEmpty();
	}

	public void pump() {
		airflow = Math.min(1f, airflow + 0.34f);
		setChanged();
	}

	public ItemStack getWorkpiece() {
		return items.get(SLOT_WORKPIECE);
	}

	public void insertWorkpiece(ItemStack stack) {
		setItem(SLOT_WORKPIECE, stack);
	}

	public ItemStack takeWorkpiece() {
		return removeItemNoUpdate(SLOT_WORKPIECE);
	}

	/** Writes the live temperature onto a stack leaving the fire. */
	public void stampHeat(ItemStack stack) {
		if (level != null && !stack.isEmpty() && Smithing.isHeatable(stack)) {
			Heat.set(level, stack, workTemp);
		}
	}

	private void resetProgress() {
		smeltProgress = 0;
		temperProgress = 0;
	}

	// --- Container ----------------------------------------------------------

	@Override
	public int getContainerSize() {
		return SLOT_COUNT;
	}

	@Override
	public boolean isEmpty() {
		return items.get(SLOT_WORKPIECE).isEmpty() && items.get(SLOT_FUEL).isEmpty();
	}

	@Override
	public ItemStack getItem(int slot) {
		return items.get(slot);
	}

	@Override
	public ItemStack removeItem(int slot, int amount) {
		ItemStack removed = ContainerHelper.removeItem(items, slot, amount);
		if (!removed.isEmpty()) {
			if (slot == SLOT_WORKPIECE) {
				stampHeat(removed);
				resetProgress();
				setChangedAndSync();
			} else {
				setChanged();
			}
		}
		return removed;
	}

	@Override
	public ItemStack removeItemNoUpdate(int slot) {
		ItemStack removed = ContainerHelper.takeItem(items, slot);
		if (!removed.isEmpty() && slot == SLOT_WORKPIECE) {
			stampHeat(removed);
			resetProgress();
			setChangedAndSync();
		}
		return removed;
	}

	@Override
	public void setItem(int slot, ItemStack stack) {
		items.set(slot, stack);
		if (stack.getCount() > stack.getMaxStackSize()) {
			stack.setCount(stack.getMaxStackSize());
		}
		if (slot == SLOT_WORKPIECE) {
			workTemp = level != null ? Heat.current(level, stack) : Heat.AMBIENT;
			resetProgress();
			setChangedAndSync();
		} else {
			setChanged();
		}
	}

	@Override
	public boolean canPlaceItem(int slot, ItemStack stack) {
		if (slot == SLOT_FUEL) {
			return stack.is(Items.COAL) || stack.is(Items.CHARCOAL);
		}
		return Smithing.isHeatable(stack);
	}

	@Override
	public boolean stillValid(Player player) {
		return Container.stillValidBlockEntity(this, player);
	}

	@Override
	public void clearContent() {
		items.clear();
	}

	// --- MenuProvider ---------------------------------------------------------

	@Override
	public Component getDisplayName() {
		return Component.translatable("block.swordsmith.forge");
	}

	@Override
	public AbstractContainerMenu createMenu(int id, Inventory playerInventory, Player player) {
		return new ForgeMenu(id, playerInventory, this, dataAccess);
	}

	// --- persistence & sync ------------------------------------------------------

	private void setChangedAndSync() {
		setChanged();
		if (level != null) {
			level.sendBlockUpdated(worldPosition, getBlockState(), getBlockState(), Block.UPDATE_CLIENTS);
		}
	}

	@Override
	protected void saveAdditional(CompoundTag tag) {
		super.saveAdditional(tag);
		ContainerHelper.saveAllItems(tag, items);
		tag.putFloat("Fuel", fuelSeconds);
		tag.putFloat("Airflow", airflow);
		tag.putFloat("ForgeTemp", forgeTemp);
		tag.putFloat("WorkTemp", workTemp);
		tag.putInt("SmeltProgress", smeltProgress);
		tag.putInt("TemperProgress", temperProgress);
	}

	@Override
	public void load(CompoundTag tag) {
		super.load(tag);
		items.clear();
		ContainerHelper.loadAllItems(tag, items);
		fuelSeconds = tag.getFloat("Fuel");
		airflow = tag.getFloat("Airflow");
		forgeTemp = tag.getFloat("ForgeTemp");
		workTemp = tag.getFloat("WorkTemp");
		smeltProgress = tag.getInt("SmeltProgress");
		temperProgress = tag.getInt("TemperProgress");
	}

	@Override
	public Packet<ClientGamePacketListener> getUpdatePacket() {
		return ClientboundBlockEntityDataPacket.create(this);
	}

	@Override
	public CompoundTag getUpdateTag() {
		return saveWithoutMetadata();
	}
}
