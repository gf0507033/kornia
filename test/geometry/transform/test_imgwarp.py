import pytest

import kornia as kornia
import kornia.testing as utils  # test utils

import torch
from torch.autograd import gradcheck
from torch.testing import assert_allclose


@pytest.mark.parametrize("batch_shape", [(1, 1, 7, 32), (2, 3, 16, 31)])
def test_warp_perspective_rotation(batch_shape, device, dtype):
    # generate input data
    batch_size, channels, height, width = batch_shape
    alpha = 0.5 * kornia.pi * torch.ones(batch_size, device=device, dtype=dtype)  # 90 deg rotation

    # create data patch
    patch = torch.rand(batch_shape, device=device, dtype=dtype)

    # create transformation (rotation)
    M = torch.eye(3, device=device, dtype=dtype).repeat(batch_size, 1, 1)  # Bx3x3
    M[:, 0, 0] = torch.cos(alpha)
    M[:, 0, 1] = -torch.sin(alpha)
    M[:, 1, 0] = torch.sin(alpha)
    M[:, 1, 1] = torch.cos(alpha)

    # apply transformation and inverse
    _, _, h, w = patch.shape
    patch_warped = kornia.warp_perspective(patch, M, dsize=(height, width), align_corners=True)
    patch_warped_inv = kornia.warp_perspective(
        patch_warped, torch.inverse(M), dsize=(height, width), align_corners=True)

    # generate mask to compute error
    mask = torch.ones_like(patch)
    mask_warped_inv = kornia.warp_perspective(
        kornia.warp_perspective(patch, M, dsize=(height, width), align_corners=True),
        torch.inverse(M),
        dsize=(height, width), align_corners=True)

    assert_allclose(mask_warped_inv * patch,
                    mask_warped_inv * patch_warped_inv, rtol=1e-4, atol=1e-4)


def test_warp_perspective_gradcheck(device, dtype):
    H, W = 5, 5
    patch = torch.rand(1, 1, 5, 5, device=device, dtype=torch.float64, requires_grad=True)
    M = kornia.eye_like(3, patch)
    assert gradcheck(kornia.warp_perspective, (patch, M, (H, W),), raise_exception=True)


@pytest.mark.parametrize("batch_size", [1, 2, 5])
def test_get_perspective_transform(batch_size, device, dtype):
    # generate input data
    h_max, w_max = 64, 32  # height, width
    h = torch.ceil(h_max * torch.rand(batch_size, device=device, dtype=dtype))
    w = torch.ceil(w_max * torch.rand(batch_size, device=device, dtype=dtype))

    norm = torch.rand(batch_size, 4, 2, device=device, dtype=dtype)
    points_src = torch.zeros_like(norm, device=device, dtype=dtype)
    points_src[:, 1, 0] = h
    points_src[:, 2, 1] = w
    points_src[:, 3, 0] = h
    points_src[:, 3, 1] = w
    points_dst = points_src + norm

    # compute transform from source to target
    dst_homo_src = kornia.get_perspective_transform(points_src, points_dst)

    assert_allclose(
        kornia.transform_points(dst_homo_src, points_src), points_dst, rtol=1e-4, atol=1e-4)

    # compute gradient check
    points_src = utils.tensor_to_gradcheck_var(points_src)  # to var
    points_dst = utils.tensor_to_gradcheck_var(points_dst)  # to var
    assert gradcheck(
        kornia.get_perspective_transform, (
            points_src,
            points_dst,
        ),
        raise_exception=True)


@pytest.mark.parametrize("batch_size", [1, 2, 5])
def test_rotation_matrix2d(batch_size, device, dtype):
    # generate input data
    center_base = torch.zeros(batch_size, 2, device=device, dtype=dtype)
    angle_base = torch.ones(batch_size, device=device, dtype=dtype)
    scale_base = torch.ones(batch_size, 2, device=device, dtype=dtype)

    # 90 deg rotation
    center = center_base
    angle = 90. * angle_base
    scale = scale_base
    M = kornia.get_rotation_matrix2d(center, angle, scale)

    for i in range(batch_size):
        assert_allclose(M[i, 0, 0].item(), 0.0, rtol=1e-4, atol=1e-4)
        assert_allclose(M[i, 0, 1].item(), 1.0, rtol=1e-4, atol=1e-4)
        assert_allclose(M[i, 1, 0].item(), -1.0, rtol=1e-4, atol=1e-4)
        assert_allclose(M[i, 1, 1].item(), 0.0, rtol=1e-4, atol=1e-4)

    # 90 deg rotation + 2x scale
    center = center_base
    angle = 90. * angle_base
    scale = 2. * scale_base
    M = kornia.get_rotation_matrix2d(center, angle, scale)

    for i in range(batch_size):
        assert_allclose(M[i, 0, 0].item(), 0.0, rtol=1e-4, atol=1e-4)
        assert_allclose(M[i, 0, 1].item(), 2.0, rtol=1e-4, atol=1e-4)
        assert_allclose(M[i, 1, 0].item(), -2.0, rtol=1e-4, atol=1e-4)
        assert_allclose(M[i, 1, 1].item(), 0.0, rtol=1e-4, atol=1e-4)

    # 45 deg rotation
    center = center_base
    angle = 45. * angle_base
    scale = scale_base
    M = kornia.get_rotation_matrix2d(center, angle, scale)

    for i in range(batch_size):
        assert_allclose(M[i, 0, 0].item(), 0.7071)
        assert_allclose(M[i, 0, 1].item(), 0.7071)
        assert_allclose(M[i, 1, 0].item(), -0.7071)
        assert_allclose(M[i, 1, 1].item(), 0.7071)

    # evaluate function gradient
    center = utils.tensor_to_gradcheck_var(center)  # to var
    angle = utils.tensor_to_gradcheck_var(angle)  # to var
    scale = utils.tensor_to_gradcheck_var(scale)  # to var
    assert gradcheck(
        kornia.get_rotation_matrix2d, (center, angle, scale),
        raise_exception=True)


class TestWarpPerspective:
    @pytest.mark.parametrize("batch_size", [1, 5])
    @pytest.mark.parametrize("channels", [1, 5])
    def test_crop(self, batch_size, channels, device, dtype):
        # generate input data
        src_h, src_w = 3, 3
        dst_h, dst_w = 3, 3

        # [x, y] origin
        # top-left, top-right, bottom-right, bottom-left
        points_src = torch.tensor([[
            [0, 0],
            [0, src_w - 1],
            [src_h - 1, src_w - 1],
            [src_h - 1, 0],
        ]], device=device, dtype=dtype)

        # [x, y] destination
        # top-left, top-right, bottom-right, bottom-left
        points_dst = torch.tensor([[
            [0, 0],
            [0, dst_w - 1],
            [dst_h - 1, dst_w - 1],
            [dst_h - 1, 0],
        ]], device=device, dtype=dtype)

        # compute transformation between points
        dst_trans_src = kornia.get_perspective_transform(points_src,
                                                         points_dst).expand(
            batch_size, -1, -1)

        # warp tensor
        patch = torch.tensor([[[
            [1, 2, 3, 4],
            [5, 6, 7, 8],
            [9, 10, 11, 12],
            [13, 14, 15, 16],
        ]]], device=device, dtype=dtype).expand(batch_size, channels, -1, -1)

        expected = torch.tensor(
            [[[[0.2500, 0.9167, 1.5833],
               [2.1667, 5.1667, 6.5000],
               [4.8333, 10.5000, 11.8333]]]], device=device, dtype=dtype)

        # warp and assert
        patch_warped = kornia.warp_perspective(patch, dst_trans_src,
                                               (dst_h, dst_w))
        assert_allclose(patch_warped, expected, rtol=1e-4, atol=1e-4)

        # check jit
        patch_warped_jit = kornia.jit.warp_perspective(patch, dst_trans_src,
                                                       (dst_h, dst_w))
        assert_allclose(patch_warped, patch_warped_jit, rtol=1e-4, atol=1e-4)

    def test_crop_center_resize(self, device, dtype):
        # generate input data
        dst_h, dst_w = 4, 4

        # [x, y] origin
        # top-left, top-right, bottom-right, bottom-left
        points_src = torch.tensor([[
            [1, 1],
            [1, 2],
            [2, 2],
            [2, 1],
        ]], device=device, dtype=dtype)

        # [x, y] destination
        # top-left, top-right, bottom-right, bottom-left
        points_dst = torch.tensor([[
            [0, 0],
            [0, dst_w - 1],
            [dst_h - 1, dst_w - 1],
            [dst_h - 1, 0],
        ]], device=device, dtype=dtype)

        # compute transformation between points
        dst_trans_src = kornia.get_perspective_transform(points_src, points_dst)

        # warp tensor
        patch = torch.tensor([[[
            [1, 2, 3, 4],
            [5, 6, 7, 8],
            [9, 10, 11, 12],
            [13, 14, 15, 16],
        ]]], device=device, dtype=dtype)

        expected = torch.tensor(
            [[[[5.1667, 5.6111, 6.0556, 6.5000],
               [6.9444, 7.3889, 7.8333, 8.2778],
               [8.7222, 9.1667, 9.6111, 10.0556],
               [10.5000, 10.9444, 11.3889, 11.8333]]]], device=device, dtype=dtype)

        # warp and assert
        patch_warped = kornia.warp_perspective(patch, dst_trans_src,
                                               (dst_h, dst_w))
        assert_allclose(patch_warped, expected, rtol=1e-4, atol=1e-4)

        # check jit
        patch_warped_jit = kornia.jit.warp_perspective(patch, dst_trans_src,
                                                       (dst_h, dst_w))
        assert_allclose(patch_warped, patch_warped_jit, rtol=1e-4, atol=1e-4)


class TestWarpAffine:
    def test_smoke(self, device, dtype):
        batch_size, channels, height, width = 1, 2, 3, 4
        aff_ab = torch.eye(2, 3, device=device, dtype=dtype)[None]  # 1x2x3
        img_b = torch.rand(batch_size, channels, height, width, device=device, dtype=dtype)
        img_a = kornia.warp_affine(img_b, aff_ab, (height, width))
        assert img_b.shape == img_a.shape

    @pytest.mark.parametrize("batch_size", [1, 2, 5])
    def test_translation(self, batch_size, device, dtype):
        offset = 1.
        channels, height, width = 1, 3, 4
        aff_ab = torch.eye(2, 3, device=device, dtype=dtype).repeat(batch_size, 1, 1)  # Bx2x3
        aff_ab[..., -1] += offset
        img_b = torch.arange(float(height * width), device=device, dtype=dtype).view(
            1, channels, height, width).repeat(batch_size, 1, 1, 1)
        img_a = kornia.warp_affine(img_b, aff_ab, (height, width), align_corners=True)
        assert_allclose(img_b[..., :2, :3], img_a[..., 1:, 1:], rtol=1e-4, atol=1e-4)

    def test_gradcheck(self, device, dtype):
        batch_size, channels, height, width = 1, 2, 3, 4
        aff_ab = torch.eye(2, 3, device=device, dtype=dtype)[None]  # 1x2x3
        img_b = torch.rand(batch_size, channels, height, width, device=device, dtype=dtype)
        aff_ab = utils.tensor_to_gradcheck_var(
            aff_ab, requires_grad=False)  # to var
        img_b = utils.tensor_to_gradcheck_var(img_b)  # to var
        assert gradcheck(
            kornia.warp_affine, (
                img_b,
                aff_ab,
                (height, width),
            ),
            raise_exception=True)


class TestRemap:
    def test_smoke(self, device, dtype):
        height, width = 3, 4
        input = torch.ones(1, 1, height, width, device=device, dtype=dtype)
        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        input_warped = kornia.remap(input, grid[..., 0], grid[..., 1], align_corners=True)
        assert_allclose(input, input_warped, rtol=1e-4, atol=1e-4)

    def test_shift(self, device, dtype):
        height, width = 3, 4
        inp = torch.tensor([[[
            [1., 1., 1., 1.],
            [1., 1., 1., 1.],
            [1., 1., 1., 1.],
        ]]], device=device, dtype=dtype)
        expected = torch.tensor([[[
            [1., 1., 1., 0.],
            [1., 1., 1., 0.],
            [0., 0., 0., 0.],
        ]]], device=device, dtype=dtype)

        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        grid += 1.  # apply shift in both x/y direction

        input_warped = kornia.remap(inp, grid[..., 0], grid[..., 1], align_corners=True)
        assert_allclose(input_warped, expected, rtol=1e-4, atol=1e-4)

    def test_shift_batch(self, device, dtype):
        height, width = 3, 4
        inp = torch.tensor([[[
            [1., 1., 1., 1.],
            [1., 1., 1., 1.],
            [1., 1., 1., 1.],
        ]]], device=device, dtype=dtype).repeat(2, 1, 1, 1)

        expected = torch.tensor([[[
            [1., 1., 1., 0.],
            [1., 1., 1., 0.],
            [1., 1., 1., 0.],
        ]], [[
            [1., 1., 1., 1.],
            [1., 1., 1., 1.],
            [0., 0., 0., 0.],
        ]]], device=device, dtype=dtype)

        # generate a batch of grids
        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        grid = grid.repeat(2, 1, 1, 1)
        grid[0, ..., 0] += 1.  # apply shift in the x direction
        grid[1, ..., 1] += 1.  # apply shift in the y direction

        input_warped = kornia.remap(inp, grid[..., 0], grid[..., 1], align_corners=True)
        assert_allclose(input_warped, expected, rtol=1e-4, atol=1e-4)

    def test_shift_batch_broadcast(self, device, dtype):
        height, width = 3, 4
        inp = torch.tensor([[[
            [1., 1., 1., 1.],
            [1., 1., 1., 1.],
            [1., 1., 1., 1.],
        ]]], device=device, dtype=dtype).repeat(2, 1, 1, 1)
        expected = torch.tensor([[[
            [1., 1., 1., 0.],
            [1., 1., 1., 0.],
            [0., 0., 0., 0.],
        ]]], device=device, dtype=dtype)

        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        grid += 1.  # apply shift in both x/y direction

        input_warped = kornia.remap(inp, grid[..., 0], grid[..., 1], align_corners=True)
        assert_allclose(input_warped, expected, rtol=1e-4, atol=1e-4)

    def test_gradcheck(self, device, dtype):
        batch_size, channels, height, width = 1, 2, 3, 4
        img = torch.rand(batch_size, channels, height, width, device=device, dtype=dtype)
        img = utils.tensor_to_gradcheck_var(img)  # to var

        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        grid = utils.tensor_to_gradcheck_var(
            grid, requires_grad=False)  # to var

        assert gradcheck(kornia.remap, (img, grid[..., 0], grid[..., 1],),
                         raise_exception=True)

    @pytest.mark.skip(reason="turn off all jit for a while")
    def test_jit(self, device, dtype):
        @torch.jit.script
        def op_script(input, map1, map2):
            return kornia.remap(input, map1, map2)
        batch_size, channels, height, width = 1, 1, 3, 4
        img = torch.ones(batch_size, channels, height, width, device=device, dtype=dtype)

        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        grid += 1.  # apply some shift

        input = (img, grid[..., 0], grid[..., 1],)
        actual = op_script(*input)
        expected = kornia.remap(*input)
        assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)

    @pytest.mark.skip(reason="turn off all jit for a while")
    def test_jit_trace(self, device, dtype):
        @torch.jit.script
        def op_script(input, map1, map2):
            return kornia.remap(input, map1, map2)
        # 1. Trace op
        batch_size, channels, height, width = 1, 1, 3, 4
        img = torch.ones(batch_size, channels, height, width, device=device, dtype=dtype)
        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        grid += 1.  # apply some shift
        input_tuple = (img, grid[..., 0], grid[..., 1])
        op_traced = torch.jit.trace(op_script, input_tuple)

        # 2. Generate different input
        batch_size, channels, height, width = 2, 2, 2, 5
        img = torch.ones(batch_size, channels, height, width, device=device, dtype=dtype)
        grid = kornia.utils.create_meshgrid(
            height, width, normalized_coordinates=False, device=device).to(dtype)
        grid += 2.  # apply some shift

        # 3. Apply to different input
        input_tuple = (img, grid[..., 0], grid[..., 1])
        actual = op_script(*input_tuple)
        expected = kornia.remap(*input_tuple)
        assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)


class TestInvertAffineTransform:
    def test_smoke(self, device, dtype):
        matrix = torch.eye(2, 3, device=device, dtype=dtype)[None]
        matrix_inv = kornia.invert_affine_transform(matrix)
        assert_allclose(matrix, matrix_inv, rtol=1e-4, atol=1e-4)

    def test_rot90(self, device, dtype):
        angle = torch.tensor([90.], device=device, dtype=dtype)
        scale = torch.tensor([[1., 1.]], device=device, dtype=dtype)
        center = torch.tensor([[0., 0.]], device=device, dtype=dtype)
        expected = torch.tensor([[
            [0., -1., 0.],
            [1., 0., 0.],
        ]], device=device, dtype=dtype)
        matrix = kornia.get_rotation_matrix2d(center, angle, scale)
        matrix_inv = kornia.invert_affine_transform(matrix)
        assert_allclose(matrix_inv, expected, rtol=1e-4, atol=1e-4)

    def test_rot90_batch(self, device, dtype):
        angle = torch.tensor([90.], device=device, dtype=dtype)
        scale = torch.tensor([[1., 1.]], device=device, dtype=dtype)
        center = torch.tensor([[0., 0.]], device=device, dtype=dtype)
        expected = torch.tensor([[
            [0., -1., 0.],
            [1., 0., 0.],
        ]], device=device, dtype=dtype)
        matrix = kornia.get_rotation_matrix2d(
            center, angle, scale).repeat(2, 1, 1)
        matrix_inv = kornia.invert_affine_transform(matrix)
        assert_allclose(matrix_inv, expected, rtol=1e-4, atol=1e-4)

    def test_gradcheck(self, device, dtype):
        matrix = torch.eye(2, 3, device=device, dtype=dtype)[None]
        matrix = utils.tensor_to_gradcheck_var(matrix)  # to var
        assert gradcheck(kornia.invert_affine_transform, (matrix,),
                         raise_exception=True)

    @pytest.mark.skip(reason="turn off all jit for a while")
    def test_jit(self, device, dtype):
        @torch.jit.script
        def op_script(input):
            return kornia.invert_affine_transform(input)
        matrix = torch.eye(2, 3, device=device, dtype=dtype)
        op_traced = torch.jit.trace(op_script, matrix)
        actual = op_traced(matrix)
        expected = kornia.invert_affine_transform(matrix)
        assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)

    @pytest.mark.skip(reason="turn off all jit for a while")
    def test_jit_trace(self, device, dtype):
        @torch.jit.script
        def op_script(input):
            return kornia.invert_affine_transform(input)
        matrix = torch.eye(2, 3, device=device, dtype=dtype)
        matrix_2 = torch.eye(2, 3, device=device, dtype=dtype).repeat(2, 1, 1)
        op_traced = torch.jit.trace(op_script, matrix)
        actual = op_traced(matrix_2)
        expected = kornia.invert_affine_transform(matrix_2)
        assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)
