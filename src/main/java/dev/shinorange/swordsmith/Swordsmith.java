package dev.shinorange.swordsmith;

import dev.shinorange.swordsmith.registry.ModBlockEntities;
import dev.shinorange.swordsmith.registry.ModBlocks;
import dev.shinorange.swordsmith.registry.ModComponents;
import dev.shinorange.swordsmith.registry.ModItemGroups;
import dev.shinorange.swordsmith.registry.ModItems;
import net.fabricmc.api.ModInitializer;
import net.minecraft.util.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Real Swordsmithing — forge a sword the way real smiths do.
 *
 * The full chain, none of it in a crafting grid:
 * raw iron -> (bloomery smelting in the forge) -> iron bloom
 * -> (hammering at forging heat on the anvil) -> billet -> preform -> rough blade
 * -> (quench at 780-950 C in the barrel) -> quenched blade
 * -> (temper at 150-400 C in the forge) -> tempered blade
 * -> (grinding on the sharpening wheel) -> sharpened blade
 * -> (hilt assembly + peening on the anvil) -> forged steel sword
 */
public class Swordsmith implements ModInitializer {
	public static final String MOD_ID = "swordsmith";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	public static Identifier id(String path) {
		return Identifier.of(MOD_ID, path);
	}

	@Override
	public void onInitialize() {
		ModComponents.init();
		ModBlocks.init();
		ModItems.init();
		ModBlockEntities.init();
		ModItemGroups.init();
		LOGGER.info("Real Swordsmithing initialized. Fire up the forge!");
	}
}
