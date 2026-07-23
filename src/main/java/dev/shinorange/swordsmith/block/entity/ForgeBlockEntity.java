package dev.shinorange.swordsmith.block.entity;

import dev.shinorange.swordsmith.block.ForgeBlock;
import dev.shinorange.swordsmith.core.Heat;
import dev.shinorange.swordsmith.core.Quality;
import dev.shinorange.swordsmith.core.Smithing;
import dev.shinorange.swordsmith.registry.ModBlockEntities;
import dev.shinorange.swordsmith.registry.ModItems;
import dev.shinorange.swordsmith.screen.ForgeScreenHandler;
import net.minecraft.block.Block;
import net.minecraft.block.BlockState;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.entity.player.PlayerInventory;
import net.minecraft.inventory.Inventories;
import net.minecraft.inventory.Inventory;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.nbt.NbtCompound;
import net.minecraft.network.listener.ClientPlayPacketListener;
import net.minecraft.network.packet.Packet;
import net.minecraft.network.packet.s2c.play.BlockEntityUpdateS2CPacket;
import net.minecraft.particle.ParticleTypes;
import net.minecraft.registry.RegistryWrapper;
import net.minecraft.screen.NamedScreenHandlerFactory;
import net.minecraft.screen.PropertyDelegate;
import net.minecraft.screen.ScreenHandler;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.sound.SoundCategory;
import net.minecraft.sound.SoundEvents;
import net.minecraft.text.Text;
import net.minecraft.util.collection.DefaultedList;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;

/**
 * Simulates the fire: fuel burns down, bellows air raises the target
 * temperature, and the workpiece asymptotically approaches the fire's
 * temperature. A lit fire without blast is a ~300 C banked fire; pumping the
 * bellows drives it toward 1280 C. Slow transformations happen in the coals:
 *
 * - bloomery smelting: raw iron held above 1150 C becomes an iron bloom
 *   (keep pumping — the blast decays)
 * - tempering: a quenched blade held at 150-400 C (the banked fire is ideal)
 *   becomes a tempered blade
 * - annealing: any hardened blade that climbs past 460 C loses its hardness
 *   and reverts to a rough blade
 *
 * Slot 0 holds the workpiece (also rendered in-world), slot 1 a stack of
 * fuel that is consumed into the fire one piece at a time. Whenever the
 * workpiece leaves through the GUI or a hopper, its live temperature is
 * stamped onto the stack — carry it with tongs.
 */
public class ForgeBlockEntity extends BlockEntity implements Inventory, NamedScreenHandlerFactory {
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

	private final DefaultedList<ItemStack> inventory = DefaultedList.ofSize(SLOT_COUNT, ItemStack.EMPTY);
	private float fuelSeconds;
	private float airflow;
	private float forgeTemp = Heat.AMBIENT;
	private float workTemp = Heat.AMBIENT;
	private int smeltProgress;
	private int temperProgress;

	private final PropertyDelegate propertyDelegate = new PropertyDelegate() {
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
			// Server-authoritative; the client handler keeps its own copy.
		}

		@Override
		public int size() {
			return PROPERTY_COUNT;
		}
	};

	public ForgeBlockEntity(BlockPos pos, BlockState state) {
		super(ModBlockEntities.FORGE, pos, state);
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

	public static void serverTick(World world, BlockPos pos, BlockState state, ForgeBlockEntity forge) {
		boolean lit = state.get(ForgeBlock.LIT);
		float target = lit ? Heat.FORGE_BASE_TEMP + forge.airflow * Heat.BELLOWS_BONUS : Heat.AMBIENT;
		forge.forgeTemp += (target - forge.forgeTemp) * 0.005f;
		forge.airflow = Math.max(0f, forge.airflow - 1f / 600f);

		if (lit) {
			// Feed the fire from the fuel slot one piece at a time.
			if (forge.fuelSeconds <= MAX_FUEL_SECONDS - FUEL_SECONDS_PER_COAL) {
				ItemStack fuel = forge.inventory.get(SLOT_FUEL);
				if (!fuel.isEmpty()) {
					fuel.decrement(1);
					forge.fuelSeconds += FUEL_SECONDS_PER_COAL;
					forge.markDirty();
				}
			}
			forge.fuelSeconds -= (1f + forge.airflow) / 20f;
			if (forge.fuelSeconds <= 0f) {
				forge.fuelSeconds = 0f;
				world.setBlockState(pos, state.with(ForgeBlock.LIT, false), Block.NOTIFY_ALL);
			}
		}

		ItemStack workpiece = forge.inventory.get(SLOT_WORKPIECE);
		if (!workpiece.isEmpty()) {
			forge.workTemp += (forge.forgeTemp - forge.workTemp) * 0.02f;
			forge.tickTransformations(world, pos);
		} else {
			forge.workTemp = forge.forgeTemp;
		}

		if (world.getTime() % 20 == 0) {
			forge.markDirty();
		}
	}

	private void tickTransformations(World world, BlockPos pos) {
		ItemStack workpiece = inventory.get(SLOT_WORKPIECE);
		if (workpiece.isOf(Items.RAW_IRON)) {
			if (workTemp >= Heat.SMELT_TEMP) {
				if (++smeltProgress >= Heat.SMELT_TICKS) {
					replaceWorkpiece(new ItemStack(ModItems.IRON_BLOOM));
					smeltProgress = 0;
					world.playSound(null, pos, SoundEvents.BLOCK_LAVA_POP, SoundCategory.BLOCKS, 1.0f, 0.8f);
					if (world instanceof ServerWorld serverWorld) {
						serverWorld.spawnParticles(ParticleTypes.LAVA,
								pos.getX() + 0.5, pos.getY() + 1.1, pos.getZ() + 0.5, 8, 0.2, 0.1, 0.2, 0.0);
					}
				}
			} else if (smeltProgress > 0 && workTemp < 700f) {
				// Only a fire left truly to die loses the smelting progress.
				smeltProgress--;
			}
		} else if (isHardenedBlade() && workTemp > Heat.ANNEAL_TEMP) {
			// Too hot: quench hardness (and any edge) is annealed away.
			replaceWorkpiece(new ItemStack(ModItems.ROUGH_BLADE));
			temperProgress = 0;
			world.playSound(null, pos, SoundEvents.BLOCK_FIRE_EXTINGUISH, SoundCategory.BLOCKS, 0.8f, 0.5f);
			if (world instanceof ServerWorld serverWorld) {
				serverWorld.spawnParticles(ParticleTypes.SMOKE,
						pos.getX() + 0.5, pos.getY() + 1.2, pos.getZ() + 0.5, 12, 0.2, 0.1, 0.2, 0.02);
			}
		} else if (workpiece.isOf(ModItems.QUENCHED_BLADE)) {
			if (workTemp >= Heat.TEMPER_MIN && workTemp <= Heat.TEMPER_MAX) {
				if (++temperProgress >= Heat.TEMPER_TICKS) {
					replaceWorkpiece(new ItemStack(ModItems.TEMPERED_BLADE));
					temperProgress = 0;
					world.playSound(null, pos, SoundEvents.ENTITY_EXPERIENCE_ORB_PICKUP, SoundCategory.BLOCKS, 0.7f, 1.2f);
				}
			}
		}
	}

	/** Blades whose heat treatment would be ruined by overheating. */
	private boolean isHardenedBlade() {
		ItemStack workpiece = inventory.get(SLOT_WORKPIECE);
		return workpiece.isOf(ModItems.QUENCHED_BLADE)
				|| workpiece.isOf(ModItems.TEMPERED_BLADE)
				|| workpiece.isOf(ModItems.SHARP_BLADE);
	}

	/** Swaps the workpiece in place, keeping its temperature and quality history. */
	private void replaceWorkpiece(ItemStack stack) {
		Quality.carry(inventory.get(SLOT_WORKPIECE), stack);
		inventory.set(SLOT_WORKPIECE, stack);
		markDirtyAndSync();
	}

	/** Tries to add one piece of fuel from the held stack into the fuel slot. */
	public boolean addFuelItem(ItemStack held) {
		ItemStack current = inventory.get(SLOT_FUEL);
		if (current.isEmpty()) {
			inventory.set(SLOT_FUEL, held.copyWithCount(1));
			markDirty();
			return true;
		}
		if (current.isOf(held.getItem()) && current.getCount() < current.getMaxCount()) {
			current.increment(1);
			markDirty();
			return true;
		}
		return false;
	}

	public boolean hasFuel() {
		return fuelSeconds > 0f || !inventory.get(SLOT_FUEL).isEmpty();
	}

	public void pump() {
		airflow = Math.min(1f, airflow + 0.34f);
		markDirty();
	}

	public ItemStack getWorkpiece() {
		return inventory.get(SLOT_WORKPIECE);
	}

	public void insertWorkpiece(ItemStack stack) {
		setStack(SLOT_WORKPIECE, stack);
	}

	/** Removes the workpiece, stamping its current temperature onto the stack. */
	public ItemStack takeWorkpiece() {
		return removeStack(SLOT_WORKPIECE);
	}

	/** Writes the live temperature onto a stack leaving the fire. */
	public void stampHeat(ItemStack stack) {
		if (world != null && !stack.isEmpty() && Smithing.isHeatable(stack)) {
			Heat.set(world, stack, workTemp);
		}
	}

	private void resetProgress() {
		smeltProgress = 0;
		temperProgress = 0;
	}

	// --- Inventory ---------------------------------------------------------

	@Override
	public int size() {
		return SLOT_COUNT;
	}

	@Override
	public boolean isEmpty() {
		return inventory.get(SLOT_WORKPIECE).isEmpty() && inventory.get(SLOT_FUEL).isEmpty();
	}

	@Override
	public ItemStack getStack(int slot) {
		return inventory.get(slot);
	}

	@Override
	public ItemStack removeStack(int slot, int amount) {
		ItemStack removed = Inventories.splitStack(inventory, slot, amount);
		if (!removed.isEmpty()) {
			if (slot == SLOT_WORKPIECE) {
				stampHeat(removed);
				resetProgress();
				markDirtyAndSync();
			} else {
				markDirty();
			}
		}
		return removed;
	}

	@Override
	public ItemStack removeStack(int slot) {
		ItemStack removed = Inventories.removeStack(inventory, slot);
		if (!removed.isEmpty() && slot == SLOT_WORKPIECE) {
			stampHeat(removed);
			resetProgress();
			markDirtyAndSync();
		}
		return removed;
	}

	@Override
	public void setStack(int slot, ItemStack stack) {
		inventory.set(slot, stack);
		if (stack.getCount() > stack.getMaxCount()) {
			stack.setCount(stack.getMaxCount());
		}
		if (slot == SLOT_WORKPIECE) {
			workTemp = world != null ? Heat.current(world, stack) : Heat.AMBIENT;
			resetProgress();
			markDirtyAndSync();
		} else {
			markDirty();
		}
	}

	@Override
	public boolean isValid(int slot, ItemStack stack) {
		if (slot == SLOT_FUEL) {
			return stack.isOf(Items.COAL) || stack.isOf(Items.CHARCOAL);
		}
		return Smithing.isHeatable(stack);
	}

	@Override
	public boolean canPlayerUse(PlayerEntity player) {
		return Inventory.canPlayerUse(this, player);
	}

	@Override
	public void clear() {
		inventory.clear();
	}

	// --- NamedScreenHandlerFactory ----------------------------------------

	@Override
	public Text getDisplayName() {
		return Text.translatable("block.swordsmith.forge");
	}

	@Override
	public ScreenHandler createMenu(int syncId, PlayerInventory playerInventory, PlayerEntity player) {
		return new ForgeScreenHandler(syncId, playerInventory, this, propertyDelegate);
	}

	// --- persistence & sync ------------------------------------------------

	private void markDirtyAndSync() {
		markDirty();
		if (world != null) {
			world.updateListeners(pos, getCachedState(), getCachedState(), Block.NOTIFY_LISTENERS);
		}
	}

	@Override
	public void writeNbt(NbtCompound nbt, RegistryWrapper.WrapperLookup registryLookup) {
		super.writeNbt(nbt, registryLookup);
		Inventories.writeNbt(nbt, inventory, registryLookup);
		nbt.putFloat("Fuel", fuelSeconds);
		nbt.putFloat("Airflow", airflow);
		nbt.putFloat("ForgeTemp", forgeTemp);
		nbt.putFloat("WorkTemp", workTemp);
		nbt.putInt("SmeltProgress", smeltProgress);
		nbt.putInt("TemperProgress", temperProgress);
	}

	@Override
	public void readNbt(NbtCompound nbt, RegistryWrapper.WrapperLookup registryLookup) {
		super.readNbt(nbt, registryLookup);
		inventory.clear();
		Inventories.readNbt(nbt, inventory, registryLookup);
		fuelSeconds = nbt.getFloat("Fuel");
		airflow = nbt.getFloat("Airflow");
		forgeTemp = nbt.getFloat("ForgeTemp");
		workTemp = nbt.getFloat("WorkTemp");
		smeltProgress = nbt.getInt("SmeltProgress");
		temperProgress = nbt.getInt("TemperProgress");
	}

	@Override
	public Packet<ClientPlayPacketListener> toUpdatePacket() {
		return BlockEntityUpdateS2CPacket.create(this);
	}

	@Override
	public NbtCompound toInitialChunkDataNbt(RegistryWrapper.WrapperLookup registryLookup) {
		return createNbt(registryLookup);
	}
}
