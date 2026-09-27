"""Logical full-grid indexing, independent of sparse cell occupancy."""

def validate_shape(cardinalities):
    if any(type(n) is not int or n <= 0 for n in cardinalities):
        raise ValueError('Grid cardinalities must be positive integers')

def flatten_index(coordinates, cardinalities):
    validate_shape(cardinalities)
    if len(coordinates) != len(cardinalities):
        raise ValueError('Coordinate rank does not match grid')
    index = 0
    for coordinate, size in zip(coordinates, cardinalities):
        if type(coordinate) is not int or not 0 <= coordinate < size:
            raise ValueError('Coordinate outside pivot grid')
        index = index * size + coordinate
    return index

def unflatten_index(index, cardinalities):
    validate_shape(cardinalities)
    if type(index) is not int or index < 0:
        raise ValueError('Cell index must be a nonnegative integer')
    coordinates = [0] * len(cardinalities)
    for d in range(len(cardinalities)-1, -1, -1):
        index, coordinates[d] = divmod(index, cardinalities[d])
    if index: raise ValueError('Cell index outside pivot grid')
    return coordinates