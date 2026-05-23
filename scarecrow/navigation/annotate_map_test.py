from scarecrow.navigation.map_unit import MapUnit


if __name__ == "__main__":
    MapUnit.annotate_map(
        "/home/itamar_hadida/scarecrow-drone/scarecrow/mapped_env/20260523_090539/map.json",
        show=True,
    )
    print("Map annotated successfully")
    